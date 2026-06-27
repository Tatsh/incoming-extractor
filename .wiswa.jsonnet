local utils = import 'utils.libjsonnet';

{
  uses_user_defaults: true,
  project_name: 'incoming-extractor',
  description: 'Extract and convert assets from the PC and Dreamcast versions of Incoming.',
  keywords: ['dreamcast', 'extractor', 'incoming', 'pvr', 'reverse engineering'],
  version: '0.0.0',
  want_main: true,
  want_flatpak: true,
  publishing+: { flathub: 'sh.tat.incoming-extractor' },
  local top = self,
  pyproject+: {
    project+: {
      scripts+: {
        'extract-pvr-pack': '%s.commands.extract_pvr_pack:extract_pvr_pack' % top.primary_module,
        ian2obj: '%s.commands.ian2obj:ian2obj' % top.primary_module,
      },
    },
    tool+: {
      coverage+: {
        report+: {
          omit+: ['%s/typing.py' % top.primary_module],
        },
        run+: {
          omit+: ['%s/typing.py' % top.primary_module],
        },
      },
      poetry+: {
        dependencies+: {
          pillow: utils.latestPypiPackageVersionCaret('pillow'),
        },
      },
    },
  },
  docs_conf+: {
    config+: {
      intersphinx_mapping+: {
        click: ['https://click.palletsprojects.com/en/stable/', null],
        PIL: ['https://pillow.readthedocs.io/en/stable/', null],
      },
    },
  },
}
