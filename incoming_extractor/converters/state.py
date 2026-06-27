"""
State converters: Incoming save, config, and snapshot files to JSON.

The schemas are reverse-engineered from the PC executable (``incoming.exe``). The configuration file
(``.cfg``) is a concatenation of fixed-size blocks described by the game's internal save-descriptor
table, so it is split into its named blocks, each decoded into a typed value (text, numeric arrays,
and the verified checksum). The snapshot files (``.sav``, ``.xxx``, and ``.lev``) are
``memcpy``-style images of a contiguous region of game globals, so a field table mapping each
global's offset, type, and name is applied. Every byte is decoded into a typed value: bytes not
covered by a known field
(gaps, large pools, and run-time pointer tables) are emitted as ``unknownAt_<offset>`` arrays of
32-bit words (or raw byte values when unaligned). Nothing is left as an opaque base64 blob.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any
import json
import logging
import operator
import struct

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

__all__ = ('cfg_to_json', 'lev_to_json', 'sav_to_json', 'xxx_to_json')

log = logging.getLogger(__name__)

_FMT_SIZE = {'b': 1, 'B': 1, 'h': 2, 'H': 2, 'i': 4, 'I': 4, 'f': 4}

# ``incoming.cfg`` (SaveGameConfigFile @ 0x46eaa0) is these blocks concatenated in order, described
# by the in-game g_pConfigSaveDescriptorTable. Each entry is (name, kind, count) where kind is a
# struct character or 'str' (a NUL-terminated text buffer); the total size is fixed.
_CFG_BLOCKS: tuple[tuple[str, str, int], ...] = (
    ('buildStamp', 'str', 32),
    ('inputAxisOptions', 'B', 224),
    ('cameraState', 'f', 57),
    ('joystickAxisBind', 'i', 96),
    ('keybindOffsets', 'i', 40),
    ('forceFeedbackDevicePresent', 'I', 1),
    ('savedMissionSlotTable', 'B', 550),
    ('highScoreTables', 'I', 2233),
    ('inputStateBlock', 'i', 28),
    ('optionValues', 'i', 5),
    ('checksum', 'I', 1),
    ('stringBuffer0', 'str', 33),
    ('stringBuffer1', 'str', 33),
    ('stringBuffer2', 'str', 33),
    ('stringBuffer3', 'str', 33),
    ('stringBuffer4', 'str', 33),
    ('stringBuffer5', 'str', 33),
    ('stringBuffer6', 'str', 33),
    ('stringBuffer7', 'str', 33),
    ('stringBuffer8', 'str', 33),
    ('stringBuffer9', 'str', 33),
)


def _cfg_block_size(kind: str, count: int) -> int:
    return count if kind == 'str' else _FMT_SIZE[kind] * count


_CFG_TOTAL = sum(_cfg_block_size(kind, count) for _, kind, count in _CFG_BLOCKS)
_CFG_CHECKSUM_BLOCK = 'highScoreTables'

# The options block is the serial/modem multiplayer connection settings (from
# UpdateOptionsMenuScreen @ 0x452148): COM port, baud rate, stop bits, parity, and flow control.
_CFG_BAUD_RATES = (110, 300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 38400, 56000, 57600, 115200,
                   128000, 256000)
_CFG_STOP_BITS = ('1', '1.5', '2')
_CFG_PARITY = ('none', 'odd', 'even', 'mark')
_CFG_FLOW_CONTROL = ('none', 'xon/xoff', 'rts', 'dtr', 'rts/dtr')

# The keybind block is 4 control-config pages of 10 action slots; each slot holds a DirectInput
# keyboard scancode (below the special base), or a special input code (at or above it). A 0 slot is
# unbound (empty name).
_KEYBIND_PAGES = 4
_KEYBIND_SLOTS_PER_PAGE = 10
_KEYBIND_SPECIAL_BASE = 0x100

# Each high-score table record is 29 dwords (116 bytes): 9 entries of {score:u32, name:char[8]} then
# a category id and a 1-based sub-index. A record whose category id is -1 terminates the arena.
_HIGH_SCORE_RECORD_SIZE = 116
_HIGH_SCORE_ENTRY_SIZE = 12
_HIGH_SCORE_ENTRY_COUNT = 9

# DirectInput keyboard scancodes (DIK_*, i.e. PS/2 set 1) to W3C ``KeyboardEvent.code`` values,
# used to make the keybind block readable.
_DIK_KEY_NAMES = {
    0x01: 'Escape',
    0x02: 'Digit1',
    0x03: 'Digit2',
    0x04: 'Digit3',
    0x05: 'Digit4',
    0x06: 'Digit5',
    0x07: 'Digit6',
    0x08: 'Digit7',
    0x09: 'Digit8',
    0x0a: 'Digit9',
    0x0b: 'Digit0',
    0x0c: 'Minus',
    0x0d: 'Equal',
    0x0e: 'Backspace',
    0x0f: 'Tab',
    0x10: 'KeyQ',
    0x11: 'KeyW',
    0x12: 'KeyE',
    0x13: 'KeyR',
    0x14: 'KeyT',
    0x15: 'KeyY',
    0x16: 'KeyU',
    0x17: 'KeyI',
    0x18: 'KeyO',
    0x19: 'KeyP',
    0x1a: 'BracketLeft',
    0x1b: 'BracketRight',
    0x1c: 'Enter',
    0x1d: 'ControlLeft',
    0x1e: 'KeyA',
    0x1f: 'KeyS',
    0x20: 'KeyD',
    0x21: 'KeyF',
    0x22: 'KeyG',
    0x23: 'KeyH',
    0x24: 'KeyJ',
    0x25: 'KeyK',
    0x26: 'KeyL',
    0x27: 'Semicolon',
    0x28: 'Quote',
    0x29: 'Backquote',
    0x2a: 'ShiftLeft',
    0x2b: 'Backslash',
    0x2c: 'KeyZ',
    0x2d: 'KeyX',
    0x2e: 'KeyC',
    0x2f: 'KeyV',
    0x30: 'KeyB',
    0x31: 'KeyN',
    0x32: 'KeyM',
    0x33: 'Comma',
    0x34: 'Period',
    0x35: 'Slash',
    0x36: 'ShiftRight',
    0x37: 'NumpadMultiply',
    0x38: 'AltLeft',
    0x39: 'Space',
    0x3a: 'CapsLock',
    0x3b: 'F1',
    0x3c: 'F2',
    0x3d: 'F3',
    0x3e: 'F4',
    0x3f: 'F5',
    0x40: 'F6',
    0x41: 'F7',
    0x42: 'F8',
    0x43: 'F9',
    0x44: 'F10',
    0x45: 'NumLock',
    0x46: 'ScrollLock',
    0x47: 'Numpad7',
    0x48: 'Numpad8',
    0x49: 'Numpad9',
    0x4a: 'NumpadSubtract',
    0x4b: 'Numpad4',
    0x4c: 'Numpad5',
    0x4d: 'Numpad6',
    0x4e: 'NumpadAdd',
    0x4f: 'Numpad1',
    0x50: 'Numpad2',
    0x51: 'Numpad3',
    0x52: 'Numpad0',
    0x53: 'NumpadDecimal',
    0x57: 'F11',
    0x58: 'F12',
    0x9c: 'NumpadEnter',
    0x9d: 'ControlRight',
    0xb5: 'NumpadDivide',
    0xb8: 'AltRight',
    0xc5: 'Pause',
    0xc7: 'Home',
    0xc8: 'ArrowUp',
    0xc9: 'PageUp',
    0xcb: 'ArrowLeft',
    0xcd: 'ArrowRight',
    0xcf: 'End',
    0xd0: 'ArrowDown',
    0xd1: 'PageDown',
    0xd2: 'Insert',
    0xd3: 'Delete'
}

# Field sub-tables for the cfg blocks that are runs of named globals (offset, name, format, count);
# decoded with the same machinery as the snapshot region. Derived from incoming.exe.
_INPUT_AXIS_OPTIONS_FIELDS: tuple[tuple[int, str, str, int], ...] = (
    (0x00, 'bInvertAxisX2', 'B', 1),
    (0x01, 'bControlConfigFlag61', 'B', 1),
    (0x04, 'dwInvertAxisY2', 'I', 1),
    (0x08, 'dwInvertAxisX3', 'I', 1),
    (0x0c, 'dwInvertAxisY3', 'I', 1),
    (0x10, 'dwMusicVolumeIndex', 'I', 1),
    (0x14, 'dwForceTerrainDraw', 'I', 1),
    (0x18, 'flMouseSensitivityX', 'f', 1),
    (0x1c, 'flMouseSensitivityY', 'f', 1),
    (0x20, 'dwForceFeedbackEnabled', 'I', 1),
    (0x24, 'dwControlConfig84', 'I', 1),
    (0x28, 'dwControlConfig88', 'I', 1),
    (0x2c, 'dwControlConfig8c', 'I', 1),
    (0x30, 'adControlModeTable', 'i', 16),
    (0x70, 'nControlConfigPage', 'i', 1),
    (0x74, 'nNetGameTypeMenuSelection', 'i', 1),
    (0x78, 'nNetSessionMenuSelection', 'i', 1),
    (0x7c, 'nModeMenuSelection', 'i', 1),
    (0x80, 'nMissionSetupSelection', 'i', 1),
    (0x84, 'bHighScoreEntryRegionByte', 'B', 1),
    (0x88, 'dwDefaultReplaySync', 'I', 1),
    (0x8c, 'dwUseObjectSpaceTransform', 'I', 1),
    (0x90, 'dwHasActiveEffectSlots', 'I', 1),
    (0x94, 'dwReplayFinished', 'I', 1),
    (0x98, 'dwLastInputCodeA', 'I', 1),
    (0x9c, 'dwLastInputCodeB', 'I', 1),
    (0xa0, 'dwRenderTerrainEnable', 'I', 1),
    (0xa4, 'dwDetailFlagA', 'I', 1),
    (0xa8, 'dwDetailFlagB', 'I', 1),
    (0xac, 'dwLowTextureDetail', 'I', 1),
    (0xb0, 'dwRenderFeatureFlag2', 'I', 1),
    (0xb4, 'dwShadowProjectConfig', 'I', 1),
    (0xb8, 'dwInputWindowReady', 'I', 1),
    (0xbc, 'dwRenderFeatureFlag4', 'I', 1),
    (0xc0, 'dwHudColorTarget', 'I', 1),
    (0xc4, 'dwControlConfigB24', 'I', 1),
    (0xc8, 'dwViewTurnRateDeg', 'I', 1),
    (0xcc, 'dwReplaySyncFlag', 'I', 1),
    (0xd0, 'dwSessionElapsedLo', 'I', 1),
    (0xd4, 'dwSessionElapsedHi', 'I', 1),
    (0xd8, 'dwMissionElapsedLo', 'I', 1),
    (0xdc, 'dwMissionElapsedHi', 'I', 1),
)
_CAMERA_STATE_FIELDS: tuple[tuple[int, str, str, int], ...] = (
    (0x00, 'flCameraPosX', 'f', 1),
    (0x04, 'flCameraPosY', 'f', 1),
    (0x08, 'flCameraPosZ', 'f', 1),
    (0x0c, 'flCameraTargetX', 'f', 1),
    (0x10, 'flCameraDefaultY', 'f', 1),
    (0x14, 'flCameraTargetZ', 'f', 1),
    (0x18, 'flCameraEyeX', 'f', 1),
    (0x1c, 'flCameraEyeY', 'f', 1),
    (0x20, 'flCameraEyeZ', 'f', 1),
    (0x24, 'flCameraLookAtX', 'f', 1),
    (0x28, 'flCameraLookAtY', 'f', 1),
    (0x2c, 'flCameraLookAtZ', 'f', 1),
    (0x30, 'flCameraYaw', 'f', 1),
    (0x34, 'flCameraPitch', 'f', 1),
    (0x3c, 'dwViewRenderMode', 'I', 1),
    (0x40, 'nReticleLockState', 'i', 1),
    (0x44, 'dwCameraFollowMode', 'I', 1),
    (0x48, 'dwGlobalStateFlags', 'I', 1),
    (0x4c, 'apLockedTargetObjects', 'I', 32),
    (0xcc, 'pReticleStateObject', 'I', 1),
    (0xd0, 'pReplayTrackedHumanObject', 'I', 1),
    (0xd4, 'pReplayTrackedFlag400Object', 'I', 1),
    (0xd8, 'dwReticleBlinkActive', 'I', 1),
    (0xdc, 'pReplayCameraObject', 'I', 1),
    (0xe0, 'pSavedReplayCameraObject', 'I', 1),
)
_JOYSTICK_AXIS_BIND_FIELDS: tuple[tuple[int, str, str, int], ...] = (
    (0x00, 'anJoystickAxisBind', 'i', 12),
    (0xb0, 'abExtendedInputState', 'B', 208),
)
_INPUT_STATE_BLOCK_FIELDS: tuple[tuple[int, str, str, int], ...] = (
    (0x00, 'adInputStateBlock', 'i', 2),
    (0x08, 'dwAnalogAxisLo', 'I', 1),
    (0x0c, 'dwAnalogAxisHi', 'I', 1),
    (0x10, 'adReplayNextInputIndex', 'i', 2),
    (0x18, 'nScoreEntryScrollB', 'i', 1),
    (0x1c, 'nScoreEntryScrollA', 'i', 1),
    (0x20, 'dwHudInfoLineCount', 'I', 1),
    (0x24, 'dwHudInfoColor', 'I', 1),
    (0x28, 'nSelectedCraftIndex', 'i', 1),
    (0x2c, 'nSelectedColorScheme', 'i', 1),
    (0x30, 'nMissionTimeLimitMinutes', 'i', 1),
    (0x34, 'dwNetGameFlags', 'I', 1),
    (0x38, 'dwSavedNetGameFlags', 'I', 1),
    (0x3c, 'dwGameSessionFlags', 'I', 1),
    (0x40, 'dwOnVictoryValue', 'I', 1),
    (0x44, 'dwOnFailureValue', 'I', 1),
    (0x48, 'dwNetControlFlags', 'I', 1),
    (0x4c, 'dwControlAuthorityMode', 'I', 1),
    (0x50, 'dwDefaultControlMode', 'I', 1),
    (0x54, 'szNetSessionName', 'str', 9),
    (0x5d, 'szNetPlayerName', 'str', 19),
)
_CFG_SUBFIELDS = {
    'inputAxisOptions': _INPUT_AXIS_OPTIONS_FIELDS,
    'cameraState': _CAMERA_STATE_FIELDS,
    'joystickAxisBind': _JOYSTICK_AXIS_BIND_FIELDS,
    'inputStateBlock': _INPUT_STATE_BLOCK_FIELDS,
}

# Field table for the mission/level snapshot region, derived from the named globals of incoming.exe
# in [g_nCurrentMissionId, g_nCurrentMissionId + 0x81a30). Each entry is (offset, name, format,
# count) where format is a struct character ('i', 'I', 'f', 'H', 'h', 'B'). Run-time pointer fields
# are decoded as unsigned 32-bit words; their saved values are not meaningful across sessions.
_SNAPSHOT_FIELDS: tuple[tuple[int, str, str, int], ...] = (
    (0x00000, 'nCurrentMissionId', 'i', 1),
    (0x00004, 'nSelectedMissionSlot', 'i', 1),
    (0x00008, 'dwGameModeFlag', 'I', 1),
    (0x0000c, 'dwNetworkMissionFlag', 'I', 1),
    (0x00010, 'dwScriptedMissionFlag', 'I', 1),
    (0x00014, 'dwDefaultScriptRuntimeRec', 'I', 1),
    (0x00018, 'wDefaultScriptRecSelector', 'H', 1),
    (0x0001a, 'wUserCameraFlag', 'H', 1),
    (0x0001c, 'nUserCameraHeroBase', 'i', 1),
    (0x00020, 'nUserCameraMode', 'i', 1),
    (0x00024, 'flUserCamViewMat00', 'f', 1),
    (0x00028, 'flUserCamViewMat01', 'f', 1),
    (0x0003c, 'flUserCamDirX', 'f', 1),
    (0x00040, 'flUserCamDirY', 'f', 1),
    (0x00044, 'flUserCamDirZ', 'f', 1),
    (0x00048, 'flUserCamEyeX', 'f', 1),
    (0x0004c, 'flUserCamEyeY', 'f', 1),
    (0x00050, 'flUserCamEyeZ', 'f', 1),
    (0x00054, 'flUserCamViewMatOut', 'f', 1),
    (0x00058, 'flUserCamViewMatOut1', 'f', 1),
    (0x00078, 'flUserCamPrevEyeX', 'f', 1),
    (0x0007c, 'flUserCamPrevEyeY', 'f', 1),
    (0x00080, 'flUserCamPrevEyeZ', 'f', 1),
    (0x00084, 'pUserCameraEyeTarget', 'I', 1),
    (0x00088, 'pUserCameraLookTarget', 'I', 1),
    (0x0008c, 'pUserCameraEyeBase', 'I', 1),
    (0x00090, 'pUserCameraLookBase', 'I', 1),
    (0x00094, 'flUserCameraFov', 'f', 1),
    (0x00098, 'flUserCamTargetX', 'f', 1),
    (0x0009c, 'flUserCamTargetY', 'f', 1),
    (0x000a0, 'flUserCamTargetZ', 'f', 1),
    (0x000e8, 'nUserCamHasBaddieScript', 'i', 1),
    (0x002dc, 'flUserCameraNear', 'f', 1),
    (0x006f0, 'nCameraLightStateBase', 'i', 1),
    (0x006f4, 'nCameraLightListStart', 'i', 1),
    (0x008b4, 'pCameraLightStateEntry0ListHead', 'I', 1),
    (0x008b8, 'flUserCamViewTargetX', 'f', 1),
    (0x008bc, 'flUserCamViewTargetY', 'f', 1),
    (0x008c0, 'flUserCamViewTargetZ', 'f', 1),
    (0x008c4, 'flUserCamSavedEyeX', 'f', 1),
    (0x008c8, 'flUserCamSavedEyeY', 'f', 1),
    (0x008cc, 'flUserCamSavedEyeZ', 'f', 1),
    (0x008d0, 'flUserCamOrbitRadius', 'f', 1),
    (0x008d4, 'nUserCameraType', 'i', 1),
    (0x008d8, 'nUserCamStateCountdown', 'i', 1),
    (0x008dc, 'dwPhaseStartClearFlagB', 'I', 1),
    (0x008e0, 'dwLocalPlayerDeathTriggered', 'I', 1),
    (0x008e8, 'dwControlRecMode', 'I', 1),
    (0x008ec, 'dwControlRecFlags', 'I', 1),
    (0x008f0, 'dwControlRecAxisX', 'I', 1),
    (0x008f4, 'dwControlRecAxisY', 'I', 1),
    (0x00948, 'adUserCameraMatrix', 'i', 1),
    (0x00978, 'adCellArray', 'I', 1),
    (0x00980, 'dwReplayStateA', 'I', 1),
    (0x00d94, 'dwUserCameraFlags', 'I', 1),
    (0x00d9c, 'dwSecondaryHeroScriptRec', 'I', 1),
    (0x00da0, 'wSecondaryScriptRecSelector', 'H', 1),
    (0x00da2, 'wReplayCamFlag', 'H', 1),
    (0x00da4, 'pSecondaryHeroRec', 'I', 1),
    (0x00da8, 'dwReplayStateB', 'I', 1),
    (0x00dac, 'adWorldPoolConfigA', 'I', 1),
    (0x00ddc, 'adWorldPoolConfigB', 'I', 1),
    (0x01478, 'dwCameraLightStateEntry1Count', 'I', 1),
    (0x0147c, 'dwCameraLightStateEntry1ListStart', 'I', 1),
    (0x0163c, 'pCameraLightStateEntry1ListHead', 'I', 1),
    (0x01640, 'flReplayCamViewTargetX', 'f', 1),
    (0x01644, 'flReplayCamViewTargetY', 'f', 1),
    (0x01648, 'flReplayCamViewTargetZ', 'f', 1),
    (0x01658, 'flReplayCamOrbitRadius', 'f', 1),
    (0x01660, 'nReplayCamStateCountdown', 'i', 1),
    (0x01664, 'dwPhaseStartClearFlagA', 'I', 1),
    (0x01670, 'dwControlAxisLoOut', 'I', 1),
    (0x01674, 'dwControlStateWord', 'I', 1),
    (0x01678, 'dwControlStateWord2', 'I', 1),
    (0x0167c, 'dwControlStateWord3', 'I', 1),
    (0x01b1c, 'dwHudOverlayFlags', 'I', 1),
    (0x01b24, 'pScriptRuntimeRec', 'I', 1),
    (0x01b28, 'dwScriptLabelRange', 'I', 1),
    (0x01b2c, 'dwScriptLabelCount', 'I', 1),
    (0x01b30, 'adBackdropCfgActive', 'I', 1),
    (0x01b34, 'flDirectLightCurY', 'f', 1),
    (0x01b38, 'flDirectLightCurZ', 'f', 1),
    (0x01b3c, 'flViewLightDirX', 'f', 1),
    (0x01b40, 'flViewLightDirY', 'f', 1),
    (0x01b44, 'flFogGradientSrc0', 'f', 1),
    (0x01b48, 'flFogGradientSrc1', 'f', 1),
    (0x01b4c, 'flFogGradientSrc2', 'f', 1),
    (0x01b50, 'flDirectLightZ', 'f', 1),
    (0x01b54, 'nBaseLightColorG', 'i', 2),
    (0x01b5c, 'nBaseLightColorB', 'i', 1),
    (0x01b60, 'flSmoothAccum1X', 'f', 1),
    (0x01b64, 'flSmoothAccum1Y', 'f', 1),
    (0x01b68, 'flSmoothAccum1Z', 'f', 1),
    (0x01b6c, 'flSmoothAccum2X', 'f', 1),
    (0x01b70, 'flSmoothAccum2Y', 'f', 1),
    (0x01b74, 'flSmoothAccum2Z', 'f', 1),
    (0x01b78, 'dwSmoothGroup2Ready', 'I', 1),
    (0x01b7c, 'flSmoothResult2X', 'f', 1),
    (0x01b80, 'flSmoothResult2Y', 'f', 1),
    (0x01b84, 'flSmoothResult2Z', 'f', 1),
    (0x01b88, 'dwSmoothGroup1Ready', 'I', 1),
    (0x01b8c, 'flSmoothResult1X', 'f', 1),
    (0x01b90, 'flSmoothResult1Y', 'f', 1),
    (0x01b94, 'flSmoothResult1Z', 'f', 1),
    (0x01b98, 'flSmoothResult1bX', 'f', 1),
    (0x01b9c, 'flSmoothResult1bY', 'f', 1),
    (0x01ba0, 'flSmoothResult1bZ', 'f', 1),
    (0x01ba4, 'dwFogColorPacked', 'I', 1),
    (0x01ba8, 'dwWorldSizeX', 'I', 1),
    (0x01bac, 'dwWorldSizeZ', 'I', 1),
    (0x01bb0, 'dwHasEarthLayer', 'I', 1),
    (0x01bb4, 'dwSmoothGroup3Ready', 'I', 1),
    (0x01bb8, 'flDirLightSmoothAccum', 'f', 1),
    (0x01bbc, 'flCloudLevelTable', 'f', 1),
    (0x01c18, 'flSmoothGroup3ZeroA', 'f', 1),
    (0x01c1c, 'flSmoothGroup3ZeroB', 'f', 1),
    (0x01c20, 'flSmoothGroup3ZeroC', 'f', 1),
    (0x01c24, 'flDirLightSmoothDelta', 'f', 1),
    (0x01c28, 'flSmoothGroup3ResultsAnchor', 'f', 1),
    (0x01c84, 'flSmoothGroup3Divisor', 'f', 1),
    (0x01c88, 'flSmoothGroup3Scale2', 'f', 1),
    (0x01c8c, 'flSmoothGroup3Scale3', 'f', 1),
    (0x01c90, 'adScoreStatsLive', 'i', 4),
    (0x01ca0, 'dwScriptScoreTotal', 'I', 1),
    (0x01ca4, 'adScoreStatsLiveTail', 'i', 8),
    (0x01cc4, 'dwScriptProcInstrTotal', 'I', 1),
    (0x01cc8, 'dwSavedProcInstrValid', 'I', 1),
    (0x01ccc, 'dwInScriptStep', 'I', 1),
    (0x01cd0, 'pCurrentProcCursor', 'I', 1),
    (0x01cd4, 'dwScriptFlagBits', 'I', 1),
    (0x01cd8, 'pWorldPoolTail', 'I', 1),
    (0x01cdc, 'pEffectFreeListHead', 'I', 1),
    (0x01ce0, 'dwActiveCellCount', 'I', 1),
    (0x01ce4, 'dwWorldSlotCount', 'I', 1),
    (0x01ce8, 'dwDebrisSimPhase', 'I', 1),
    (0x01cec, 'nScriptInstrCount', 'i', 1),
    (0x01cf0, 'nScriptActiveProcSlot', 'i', 1),
    (0x01cf4, 'nScriptLabelCount', 'i', 1),
    (0x01cf8, 'nScriptLabelTotal', 'i', 1),
    (0x01cfc, 'dwMissionCountdownActive', 'I', 1),
    (0x01d00, 'nMissionCountdownTimer', 'i', 1),
    (0x01d04, 'dwRadarFlashTimer', 'I', 1),
    (0x01d08, 'dwFrameCounter', 'I', 1),
    (0x01d0c, 'dwSimTickCounter', 'I', 1),
    (0x01d10, 'dwFrameSequence', 'I', 1),
    (0x01d14, 'dwScriptTimerMode', 'I', 1),
    (0x01d18, 'nLevelMsgValue', 'i', 1),
    (0x01d1c, 'pPlayerRecord', 'I', 1),
    (0x01d20, 'dwPlayerHitFlashTimer', 'I', 1),
    (0x01d24, 'flDebrisViewTargetX', 'f', 1),
    (0x01d28, 'flDebrisViewTargetY', 'f', 1),
    (0x01d2c, 'flDebrisViewTargetZ', 'f', 1),
    (0x01d30, 'dwSnapshotCdTrack', 'I', 1),
    (0x01d34, 'dwScriptDataSize', 'I', 1),
    (0x01d38, 'dwLastEmittedCmdNode', 'I', 1),
    (0x01d40, 'dwInProcedureFlag', 'I', 1),
    (0x01d44, 'pLastSpawnedObject', 'I', 1),
    (0x01d48, 'pCurrentWeaponRec', 'I', 1),
    (0x01d4c, 'pCurrentLabelObject', 'I', 1),
    (0x01d50, 'dwHasWaypoint', 'I', 1),
    (0x01d54, 'dwWaypointData', 'I', 7),
    (0x01d70, 'pWorldPoolActiveEndAlias', 'I', 1),
    (0x01d74, 'dwEffectSlotStateArray', 'I', 1),
    (0x01d78, 'pEffectSlotPoolBase', 'I', 1),
    (0x01d88, 'adEffectSlotField14', 'i', 1),
    (0x01d9c, 'adEffectSlotField28', 'i', 1),
    (0x01da4, 'flEffectSlotTorqueX', 'f', 1),
    (0x01da8, 'flEffectSlotTorqueY', 'f', 1),
    (0x01dac, 'flEffectSlotTorqueZ', 'f', 1),
    (0x01db8, 'dwEffectSlotAuxArray', 'I', 1),
    (0x01dd0, 'flEffectSlotVelX', 'f', 1),
    (0x01dd4, 'flEffectSlotVelZ', 'f', 1),
    (0x01dd8, 'flEffectSlotVelY', 'f', 1),
    (0x01e00, 'apEffectSlotDynamics', 'i', 1),
    (0x01e0c, 'adEffectSlotField98', 'I', 1),
    (0x01e1c, 'anBuildingTable', 'i', 1),
    (0x01e20, 'adEffectSlotField80', 'I', 1),
    (0x01e24, 'flEffectSlotXformBase', 'f', 1),
    (0x01e30, 'adEffectSlotMinImpact', 'I', 1),
    (0x01e34, 'adPlayerRecordField3', 'I', 1),
    (0x01e38, 'adPlayerRecordField2', 'I', 1),
    (0x01e3c, 'adPlayerRecordScanBase', 'I', 1),
    (0x01e40, 'adPlayerRecordField1', 'I', 1),
    (0x01e44, 'wPlayerRecordPackedField', 'H', 1),
    (0x01e48, 'adPlayerRecordField0', 'I', 1),
    (0x01f08, 'adPlayerRecordNextField3', 'I', 1),
    (0x01f0c, 'adPlayerRecordNextField2', 'I', 1),
    (0x01f10, 'adPlayerRecordNextField1', 'I', 1),
    (0x01f14, 'adPlayerRecordNextField0', 'I', 1),
    (0x02204, 'nCameraLightListEnd', 'i', 1),
    (0x03724, 'dwEffectSlotPoolEndMarker', 'I', 1),
    (0x037f4, 'adWorldGrid', 'I', 1),
    (0x038bc, 'adPlayerRecordArrayEnd', 'I', 1),
    (0x13728, 'dwWorldPoolGridNodeBase', 'I', 1),
    (0x1372c, 'dwWorldPoolGridNodeNext', 'I', 1),
    (0x137f0, 'awWorldPoolRecordHead', 'H', 1),
    (0x137f2, 'wWorldPoolRecordStateFlags', 'H', 1),
    (0x137f4, 'awWorldObjectPool', 'H', 1),
    (0x137f6, 'awWorldPoolField02', 'H', 1),
    (0x137f8, 'awWorldPoolField04', 'I', 1),
    (0x137fc, 'awWorldPoolField08', 'I', 1),
    (0x13800, 'awWorldPoolField0C', 'I', 1),
    (0x13804, 'awWorldPoolField10', 'i', 1),
    (0x13808, 'awWorldPoolField14', 'I', 1),
    (0x1380c, 'awWorldPoolField18', 'I', 1),
    (0x13810, 'awWorldPoolField1c', 'I', 1),
    (0x1383c, 'awWorldPoolField48', 'I', 1),
    (0x13840, 'awWorldPoolField4c', 'I', 1),
    (0x1386c, 'awWorldPoolField78', 'f', 1),
    (0x13870, 'awWorldPoolField7C', 'f', 1),
    (0x13874, 'awWorldPoolField80', 'f', 1),
    (0x13878, 'awWorldPoolField84', 'f', 1),
    (0x1387c, 'awWorldPoolField88', 'f', 1),
    (0x13880, 'awWorldPoolField8C', 'f', 1),
    (0x13890, 'awWorldPoolField9C', 'I', 1),
    (0x13894, 'awWorldPoolFieldA0', 'I', 1),
    (0x13898, 'awWorldPoolFieldA4', 'I', 1),
    (0x1389c, 'awWorldPoolFieldA8', 'I', 1),
    (0x138a8, 'awWorldPoolRec1Field54', 'H', 1),
    (0x138ac, 'anWorldPoolFieldB8', 'i', 1),
    (0x138b0, 'awWorldPoolRec1Field5c', 'H', 1),
    (0x138bc, 'awWorldPoolFieldC8', 'H', 1),
    (0x138be, 'abWorldPoolFlagsCA', 'B', 1),
    (0x138c0, 'awWorldPoolRec1Base', 'I', 1),
    (0x138d0, 'awWorldPoolRec1Field7c', 'H', 1),
    (0x13974, 'awWorldPoolRec1Field80', 'H', 1),
    (0x1397c, 'awWorldPoolRec1Field88', 'H', 1),
    (0x1398a, 'awWorldPoolRec1Field96', 'H', 1),
    (0x682a4, 'anColorKeyRefCount', 'i', 30),
    (0x68c90, 'abMissionScriptDataPool', 'B', 1),
    (0x80c90, 'abScriptDataBuffer', 'B', 1),
    (0x80cb0, 'flDebrisLeadVelX', 'f', 1),
    (0x80cb4, 'flDebrisLeadVelY', 'f', 1),
    (0x80cb8, 'flDebrisLeadVelZ', 'f', 1),
    (0x80cbc, 'flDebrisLeadPosX', 'f', 1),
    (0x80cc0, 'flDebrisLeadPosY', 'f', 1),
    (0x80cc4, 'flDebrisLeadPosZ', 'f', 1),
    (0x80cc8, 'flDebrisLeadDeltaX', 'f', 1),
    (0x80ccc, 'flDebrisLeadDeltaY', 'f', 1),
    (0x80cd0, 'flDebrisLeadDeltaZ', 'f', 1),
    (0x80cd4, 'flDebrisLeadResidualX', 'f', 1),
    (0x80cd8, 'flDebrisLeadResidualY', 'f', 1),
    (0x80cdc, 'flDebrisLeadResidualZ', 'f', 1),
    (0x80d08, 'flDebrisParticleArray', 'f', 1),
    (0x80f2c, 'dwDebrisLeadColor0', 'I', 1),
    (0x80f30, 'dwDebrisLeadColor1', 'I', 1),
    (0x80f34, 'dwDebrisLeadColor2', 'I', 1),
    (0x80f54, 'dwDebrisLeadReseed0', 'I', 1),
    (0x80f5c, 'dwDebrisLeadReseed1', 'I', 1),
    (0x80f7c, 'flDebrisParticleArrayEnd', 'f', 1),
    (0x80f84, 'flDebrisParticleScale', 'f', 1),
    (0x80fbc, 'pGenerationPointsList', 'I', 1),
    (0x80fc0, 'apActiveObjectList', 'I', 30),
    (0x81038, 'nActiveObjectCount', 'i', 1),
    (0x8103c, 'dwWorldStateFlags', 'I', 1),
    (0x81040, 'flCameraPosX', 'f', 1),
    (0x81044, 'flCameraPosY', 'f', 1),
    (0x81048, 'flCameraPosZ', 'f', 1),
    (0x8104c, 'flCameraTargetX', 'f', 1),
    (0x81050, 'flCameraDefaultY', 'f', 1),
    (0x81054, 'flCameraTargetZ', 'f', 1),
    (0x81058, 'flCameraEyeX', 'f', 1),
    (0x8105c, 'flCameraEyeY', 'f', 1),
    (0x81060, 'flCameraEyeZ', 'f', 1),
    (0x81064, 'flCameraLookAtX', 'f', 1),
    (0x81068, 'flCameraLookAtY', 'f', 1),
    (0x8106c, 'flCameraLookAtZ', 'f', 1),
    (0x81070, 'flCameraYaw', 'f', 1),
    (0x81074, 'flCameraPitch', 'f', 1),
    (0x8107c, 'dwViewRenderMode', 'I', 1),
    (0x81080, 'nReticleLockState', 'i', 1),
    (0x81084, 'dwCameraFollowMode', 'I', 1),
    (0x81088, 'dwGlobalStateFlags', 'I', 1),
    (0x8108c, 'apLockedTargetObjects', 'I', 32),
    (0x8110c, 'pReticleStateObject', 'I', 1),
    (0x81110, 'pReplayTrackedHumanObject', 'I', 1),
    (0x81114, 'pReplayTrackedFlag400Object', 'I', 1),
    (0x81118, 'dwReticleBlinkActive', 'I', 1),
    (0x8111c, 'pReplayCameraObject', 'I', 1),
    (0x81120, 'pSavedReplayCameraObject', 'I', 1),
    (0x81124, 'nActiveCameraLightCount', 'i', 1),
    (0x81128, 'dwLockCameraTargetId', 'I', 1),
    (0x8112c, 'dwLastDeviceCreateFrame', 'I', 1),
    (0x81130, 'flSparkDebrisMatrixPool', 'f', 576),
)

# The .sav/.xxx region begins 12 bytes before the .lev region (the leading mission-id fields), so
# both end at the same global; .lev shares this field table shifted by this prefix.
_LEVEL_PREFIX = 12
_MISSION_SNAPSHOT_SIZE = 0x81a30
_LEVEL_SNAPSHOT_SIZE = 0x81a24


def _write_json(source: Path, dest_dir: Path, obj: dict[str, Any]) -> Path:
    destination = dest_dir / f'{source.stem}.json'
    destination.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return destination


def _unpack(data: bytes, pos: int, fmt: str, count: int) -> Any:
    if fmt == 'str':
        return data[pos:pos + count].split(b'\x00', 1)[0].decode('latin-1')
    values = struct.unpack_from(f'<{count}{fmt}', data, pos)
    return values[0] if count == 1 else list(values)


def _decode_gap(data: bytes, start: int, end: int) -> Any:
    # Every byte must be decoded, never left as an opaque blob. The region is a 32-bit-aligned RAM
    # image, so an aligned, word-multiple span decodes as unsigned 32-bit words; anything else
    # decodes as raw byte values.
    span = data[start:end]
    if start % 4 == 0 and len(span) % 4 == 0:
        return list(struct.unpack(f'<{len(span) // 4}I', span))
    return list(span)


def _decode_region(data: bytes, fields: Sequence[tuple[int, str, str, int]],
                   base: int) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    items = sorted(
        ((off - base, name, fmt, count) for off, name, fmt, count in fields if off - base >= 0),
        key=operator.itemgetter(0))
    cursor = 0
    for pos, name, fmt, count in items:
        size = _cfg_block_size(fmt, count)
        if pos + size > len(data):
            break
        if pos > cursor:
            decoded[f'unknownAt_{cursor:06x}'] = _decode_gap(data, cursor, pos)
        decoded[name] = _unpack(data, pos, fmt, count)
        cursor = pos + size
    if cursor < len(data):
        decoded[f'unknownAt_{cursor:06x}'] = _decode_gap(data, cursor, len(data))
    return decoded


def _snapshot_to_json(source: Path, dest_dir: Path, fmt: str, base: int,
                      expected_size: int) -> Path:
    data = source.read_bytes()
    obj = {
        'format': fmt,
        'size': len(data),
        'expected_size': expected_size,
        'fields': _decode_region(data, _SNAPSHOT_FIELDS, base),
    }
    return _write_json(source, dest_dir, obj)


def sav_to_json(source: Path, dest_dir: Path) -> Path:
    """
    Convert an Incoming ``.sav`` save game to JSON.

    The mission-state snapshot region (``SaveMissionStateSnapshot``) is decoded into named fields;
    bytes not covered by a known field are kept as base64 ``raw_regions``.

    Parameters
    ----------
    source : Path
        The source ``.sav`` file.
    dest_dir : Path
        The directory the JSON is written to.

    Returns
    -------
    Path
        The written JSON path.
    """
    return _snapshot_to_json(source, dest_dir, 'incoming-save', 0, _MISSION_SNAPSHOT_SIZE)


def xxx_to_json(source: Path, dest_dir: Path) -> Path:
    """
    Convert an Incoming ``.xxx`` debug mission snapshot to JSON.

    The ``.xxx`` file uses the same mission-state snapshot format as ``.sav``, so it shares that
    decoder; bytes not covered by a known field are kept as base64 ``raw_regions``.

    Parameters
    ----------
    source : Path
        The source ``.xxx`` file.
    dest_dir : Path
        The directory the JSON is written to.

    Returns
    -------
    Path
        The written JSON path.
    """
    return _snapshot_to_json(source, dest_dir, 'incoming-debug-snapshot', 0, _MISSION_SNAPSHOT_SIZE)


def lev_to_json(source: Path, dest_dir: Path) -> Path:
    """
    Convert an Incoming ``.lev`` level-state snapshot to JSON.

    The level snapshot (``SaveLevelStateSnapshot``) shares the mission-snapshot field table without
    its 12-byte mission-id prefix; bytes not covered by a known field are kept as base64
    ``raw_regions``.

    Parameters
    ----------
    source : Path
        The source ``.lev`` file.
    dest_dir : Path
        The directory the JSON is written to.

    Returns
    -------
    Path
        The written JSON path.
    """
    return _snapshot_to_json(source, dest_dir, 'incoming-level-snapshot', _LEVEL_PREFIX,
                             _LEVEL_SNAPSHOT_SIZE)


def _decode_keybind(scancode: int) -> dict[str, Any]:
    if scancode == 0:
        name = ''
    elif scancode >= _KEYBIND_SPECIAL_BASE:
        name = f'special{scancode - _KEYBIND_SPECIAL_BASE + 1}'
    else:
        name = _DIK_KEY_NAMES.get(scancode, f'scancode_{scancode:#04x}')
    return {'directInputScancode': scancode, 'name': name}


def _decode_keybinds(values: Sequence[int]) -> list[list[dict[str, Any]]]:
    return [[
        _decode_keybind(values[page * _KEYBIND_SLOTS_PER_PAGE + slot])
        for slot in range(_KEYBIND_SLOTS_PER_PAGE)
    ] for page in range(_KEYBIND_PAGES)]


def _option_label(options: Sequence[str], index: int) -> str | int:
    return options[index] if 0 <= index < len(options) else index


def _decode_serial_options(values: Sequence[int]) -> dict[str, Any]:
    com_port, baud, stop_bits, parity, flow_control = values
    return {
        'comPort': com_port + 1,
        'baudRate': _CFG_BAUD_RATES[baud] if 0 <= baud < len(_CFG_BAUD_RATES) else baud,
        'stopBits': _option_label(_CFG_STOP_BITS, stop_bits),
        'parity': _option_label(_CFG_PARITY, parity),
        'flowControl': _option_label(_CFG_FLOW_CONTROL, flow_control),
    }


def _decode_high_score_tables(raw: bytes) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for start in range(0, len(raw) - _HIGH_SCORE_RECORD_SIZE + 1, _HIGH_SCORE_RECORD_SIZE):
        record = raw[start:start + _HIGH_SCORE_RECORD_SIZE]
        category_id = int.from_bytes(record[108:112], 'little', signed=True)
        if category_id == -1:
            break
        entries = [{
            'score':
                int.from_bytes(record[entry:entry + 4], 'little'),
            'name':
                record[entry + 4:entry + _HIGH_SCORE_ENTRY_SIZE].split(b'\x00', 1)
                [0].decode('latin-1'),
        } for entry in range(0, _HIGH_SCORE_ENTRY_SIZE *
                             _HIGH_SCORE_ENTRY_COUNT, _HIGH_SCORE_ENTRY_SIZE)]
        tables.append({
            'categoryId': category_id,
            'subIndex': int.from_bytes(record[112:116], 'little', signed=True),
            'entries': entries,
        })
    return tables


def cfg_to_json(source: Path, dest_dir: Path) -> Path:
    """
    Convert an Incoming ``.cfg`` configuration file to JSON.

    The file (``SaveGameConfigFile``) is a concatenation of fixed-size blocks. Each block is decoded
    into a human-readable value: the build stamp and trailing buffers as text; the keybind block as
    four control-config pages of ten slots, each a DirectInput scancode with its key name; the
    options block as the serial/modem connection settings (COM port, baud rate, stop bits, parity,
    and flow control); the high-score block as a list of tables of ``{score, name}`` entries; the
    force-feedback flag as a boolean; and the checksum as an object that recomputes and verifies it.
    Nothing is left as an opaque blob.

    Parameters
    ----------
    source : Path
        The source ``.cfg`` file.
    dest_dir : Path
        The directory the JSON is written to.

    Returns
    -------
    Path
        The written JSON path.
    """
    data = source.read_bytes()
    obj: dict[str, Any] = {
        'format': 'incoming-config',
        'size': len(data),
        'expected_size': _CFG_TOTAL
    }
    if len(data) != _CFG_TOTAL:
        log.warning('Config `%s` is %d bytes, expected %d; decoding as raw words.', source,
                    len(data), _CFG_TOTAL)
        obj['raw'] = _decode_gap(data, 0, len(data))
        return _write_json(source, dest_dir, obj)
    blocks: dict[str, Any] = {}
    offsets: dict[str, tuple[int, int]] = {}
    cursor = 0
    for name, kind, count in _CFG_BLOCKS:
        size = _cfg_block_size(kind, count)
        offsets[name] = (cursor, size)
        if kind == 'str':
            blocks[name] = data[cursor:cursor + size].split(b'\x00', 1)[0].decode('latin-1')
        else:
            blocks[name] = _unpack(data, cursor, kind, count)
        cursor += size
    # Decode specific blocks into human-readable forms.
    blocks['forceFeedbackDevicePresent'] = bool(blocks['forceFeedbackDevicePresent'])
    blocks['keybindOffsets'] = _decode_keybinds(blocks['keybindOffsets'])
    blocks['optionValues'] = _decode_serial_options(blocks['optionValues'])
    for name, fields in _CFG_SUBFIELDS.items():
        block_offset, block_size = offsets[name]
        blocks[name] = _decode_region(data[block_offset:block_offset + block_size], fields, 0)
    check_offset, check_size = offsets[_CFG_CHECKSUM_BLOCK]
    blocks['highScoreTables'] = _decode_high_score_tables(
        data[check_offset:check_offset + check_size])
    stored = blocks['checksum']
    computed = sum(struct.unpack_from(f'<{check_size}b', data, check_offset)) & 0xFFFFFFFF
    blocks['checksum'] = {'stored': stored, 'computed': computed, 'valid': stored == computed}
    obj['blocks'] = blocks
    return _write_json(source, dest_dir, obj)
