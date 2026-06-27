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
        size = _FMT_SIZE[fmt] * count
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


def cfg_to_json(source: Path, dest_dir: Path) -> Path:
    """
    Convert an Incoming ``.cfg`` configuration file to JSON.

    The file (``SaveGameConfigFile``) is a concatenation of fixed-size blocks. Each block is decoded
    into a typed value: the build stamp and the trailing buffers as text, numeric blocks as arrays,
    and the high-score checksum as an object that also recomputes and verifies it. Nothing is left
    as an opaque blob.

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
    checksum_block_offset = checksum_block_size = 0
    cursor = 0
    for name, kind, count in _CFG_BLOCKS:
        size = _cfg_block_size(kind, count)
        if name == _CFG_CHECKSUM_BLOCK:
            checksum_block_offset, checksum_block_size = cursor, size
        if kind == 'str':
            blocks[name] = data[cursor:cursor + size].split(b'\x00', 1)[0].decode('latin-1')
        else:
            blocks[name] = _unpack(data, cursor, kind, count)
        cursor += size
    stored = blocks['checksum']
    computed = sum(struct.unpack_from(f'<{checksum_block_size}b', data,
                                      checksum_block_offset)) & 0xFFFFFFFF
    blocks['checksum'] = {'stored': stored, 'computed': computed, 'valid': stored == computed}
    obj['blocks'] = blocks
    return _write_json(source, dest_dir, obj)
