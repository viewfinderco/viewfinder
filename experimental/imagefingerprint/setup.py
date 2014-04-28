from distutils.core import setup, Extension

extension = Extension(
  name='imagefingerprint',
  sources=['ImageFingerprint.cc',
           'imagefingerprintmodule.cc',
           ],
  extra_compile_args=['-Wno-unused-variable'],
  extra_link_args=['-framework', 'CoreGraphics',
                   '-framework', 'Accelerate',
                   '-framework', 'ImageIO',
                   ],
  )

setup(name='imagefingerprint',
      version='0.1',
      ext_modules=[extension])
