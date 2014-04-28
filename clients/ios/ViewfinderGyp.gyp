{
  'target_defaults': {
    # Things get confused if multiple targets in the same .gyp file don't have the same configuration
    # names, so define them all here.  (this problem doesn't appear to exist across .gyp files,
    # and it doesn't work to define configurations in globals.gypi).
    'default_configuration': 'Debug',
    'configurations': {
      'Debug': {
      },
      'Release': {
      },
      'Ad-hoc': {
      },
      'AppStore': {
      },
      'Enterprise': {
      },
    },
  },
  'targets': [
    {
      'target_name': 'protos',
      'type': 'static_library',
      'includes': [
        '../shared/protoc.gypi',
      ],
      'dependencies': [
	'third_party_shared/protobuf.gyp:libprotobuf',
	'../shared/shared.gyp:libshared',
      ],
      'sources': [
        '<!@(ls Source/*.proto)',
      ],
    },
    {
      'target_name': 'Viewfinder',
      'type': 'executable',
      'mac_bundle': 1,
      'actions': [
        {
          'action_name': 'version-info',
          'inputs': [],
          'outputs': [
            '${INTERMEDIATE_DIR}/ALWAYS-RUN',
            '${INTERMEDIATE_DIR}/Viewfinder-Version.plist',
          ],
          'action': ['bash', 'scripts/version-info-gyp.sh'],
        },
      ],
      'postbuilds': [
        {
          'postbuild_name': 'simulator-only-resources',
          'action': [ 'bash', 'scripts/simulator-only-resources-gyp.sh' ],
        },
      ],
      'dependencies': [
        'protos',
        'third_party/facebook.gyp:libfacebook',
        'third_party/gdata.gyp:libgdata',
        'third_party/mongoose.gyp:libmongoose',
        'third_party/plcrashreporter.gyp:libplcrashreporter',
      ],
      'include_dirs': [
        '.',
        'Source',
        'Source/Tests',
        # INTERMEDIATE_DIR is used by actions within this target (i.e. developer-defines), and
        # SHARED_INTERMEDIATE_DIR is used by other targets (protos)
        '${INTERMEDIATE_DIR}',
        '${SHARED_INTERMEDIATE_DIR}',
        '${SDKROOT}/usr/include/libxml2',
      ],
      'xcode_settings': {
        'INFOPLIST_FILE': 'Source/Viewfinder-Info.plist',
        'CLANG_ENABLE_OBJC_ARC': 'YES',
        'LIBRARY_SEARCH_PATHS': [
        ],
        'OTHER_LDFLAGS': [
          '-ObjC',
          '-lz',
        ],
        'ALWAYS_SEARCH_USER_PATHS': 'NO',
        'CLANG_ANALYZER_SECURITY_FLOATLOOPCOUNTER': 'YES',
        'CLANG_ANALYZER_SECURITY_INSECUREAPI_RAND': 'YES',
        'CLANG_ANALYZER_SECURITY_INSECUREAPI_STRCPY': 'YES',
        'CLANG_WARN_OBJC_IMPLICIT_ATOMIC_PROPERTIES': 'YES',
        'CLANG_WARN_OBJC_MISSING_PROPERTY_SYNTHESIS': 'YES',
        'DEAD_CODE_STRIPPING': 'YES',
        'EXPORTED_SYMOBLS_FILE': '',
        'GCC_C_LANGUAGE_STANDARD': 'gnu99',
        'GCC_DYNAMIC_NO_PIC': 'NO',
        'GCC_ENABLE_CPP_EXCEPTIONS': 'NO',
        'GCC_ENABLE_CPP_RTTI': 'YES',
        'GCC_ENABLE_OBJC_EXCEPTIONS': 'NO',
        'GCC_INLINES_ARE_PRIVATE_EXTERN': 'NO',
        'GCC_PRECOMPILE_PREFIX_HEADER': 'YES',
        'GCC_PREFIX_HEADER': 'Source/Viewfinder-Prefix.pch',
        'GCC_TREAT_WARNINGS_AS_ERRORS': 'YES',
        'GCC_WARN_ABOUT_MISSING_FIELD_INITIALIZERS': 'NO',
        'GCC_WARN_ABOUT_MISSING_PROTOTYPES': 'YES',
        'GCC_WARN_ABOUT_RETURN_TYPE': 'YES',
        'GCC_WARN_NON_VIRTUAL_DESTRUCTOR': 'YES',
        'GCC_WARN_UNUSED_VARIABLE': 'YES',
        'KEEP_PRIVATE_EXTERNS': 'NO',
        'SKIP_INSTALL': 'NO',
        'TARGETED_DEVICE_FAMILY': '1',
        'WARNING_CFLAGS': [
          '-Wall',
          '-Wextra',
          '-Warc-retain-cycles',
          '-Wno-sign-compare',
          '-Wno-unused-parameter',
          '-Wno-missing-field-initializers',
          '-Wno-c++11-narrowing',
        ],
      },
      # The following fields can be set in a configuration:
      #   defines
      #   include_dirs
      #   mac_framework_dirs
      #   xcode_config_file
      #   xcode_settings
      # Other fields included in configurations may be silently ignored.
      # New dependencies and source files cannot be added here; all dependencies must be
      # included in all configurations and then controlled with #ifdefs (as in "#ifdef TESTING"),
      # or for prebuilt libraries a -l linker flag (as in -lTestFlight).
      'configurations': {
        'Debug': {
          'xcode_settings': {
            'CODE_SIGN_ENTITLEMENTS': 'Source/Viewfinder-devel.entitlements',
            'CODE_SIGN_IDENITTY': 'iOS Developer',
            #'PROVISIONING_PROFILE': '<!(scripts/get_provisioning_profile.sh "Viewfinder Dev")',
            'OTHER_LDFLAGS': [
              '-L$(SRCROOT)/third_party/TestFlight',
              '-lTestFlight',
            ],
            'STRIP_STYLE': 'non-global',
          },
          'defines': [
            'DEBUG=1',
            'TESTING=1',
            'DEVELOPMENT=1',
          ],
          'include_dirs': [
            'third_party',  # for TestFlight/TestFlight.h
          ],
        },
        'Release': {
          'xcode_settings': {
            'CODE_SIGN_ENTITLEMENTS': 'Source/Viewfinder-devel.entitlements',
            'CODE_SIGN_IDENITTY': 'iOS Developer',
            #'PROVISIONING_PROFILE': '<!(scripts/get_provisioning_profile.sh "Viewfinder Dev")',
          },
          'defines': [
            'APPSTORE=1',
            'DEVELOPMENT=1',
          ],
        },
        'AppStore': {
          'xcode_settings': {
            'CODE_SIGN_ENTITLEMENTS': 'Source/Viewfinder-dist.entitlements',
            'CODE_SIGN_IDENTITY': 'iPhone Distribution: Minetta LLC',
            #'PROVISIONING_PROFILE': '<!(scripts/get_provisioning_profile.sh "Viewfinder Distribution")',
          },
          'defines': [
            'APPSTORE=1',
          ],
        },
        'Enterprise': {
          'xcode_settings': {
            'CODE_SIGN_ENTITLEMENTS': 'Source/Viewfinder-enterprise.entitlements',
            'CODE_SIGN_IDENTITY': 'iPhone Distribution: Minetta, LLC',
            #'PROVISIONING_PROFILE': '<!(scripts/get_provisioning_profile.sh "Viewfinder Enterprise")',
            'PRODUCT_NAME': 'ViewfinderTest',
          },
          'defines': [
            'APPSTORE=1',
            'ENTERPRISE=1',
          ],
        },
        'Ad-hoc': {
          'xcode_settings': {
            'CODE_SIGN_ENTITLEMENTS': 'Source/Viewfinder-dist.entitlements',
            'CODE_SIGN_IDENTITY': 'iPhone Distribution: Minetta LLC',
            #'PROVISIONING_PROFILE': '<!(scripts/get_provisioning_profile.sh "Viewfinder Ad Hoc")',
            'OTHER_LDFLAGS': [
              '-L$(SRCROOT)/third_party/TestFlight',
              '-lTestFlight',
            ],
          },
          'include_dirs': [
            'third_party',  # for TestFlight/TestFlight.h
          ],
          'defines': [
            'ADHOC=1',
          ],
        },
      },
      'link_settings': {
        'libraries': [
          '${SDKROOT}/System/Library/Frameworks/AddressBook.framework',
          '${SDKROOT}/System/Library/Frameworks/Accelerate.framework',
          '${SDKROOT}/System/Library/Frameworks/AssetsLibrary.framework',
          '${SDKROOT}/System/Library/Frameworks/AVFoundation.framework',
          '${SDKROOT}/System/Library/Frameworks/AudioToolbox.framework',
          '${SDKROOT}/System/Library/Frameworks/CoreGraphics.framework',
          '${SDKROOT}/System/Library/Frameworks/CoreImage.framework',
          '${SDKROOT}/System/Library/Frameworks/CoreLocation.framework',
          '${SDKROOT}/System/Library/Frameworks/CoreMedia.framework',
          '${SDKROOT}/System/Library/Frameworks/CoreTelephony.framework',
          '${SDKROOT}/System/Library/Frameworks/CoreText.framework',
          '${SDKROOT}/System/Library/Frameworks/CoreVideo.framework',
          '${SDKROOT}/System/Library/Frameworks/GLKit.framework',
          '${SDKROOT}/System/Library/Frameworks/ImageIO.framework',
          '${SDKROOT}/System/Library/Frameworks/MediaPlayer.framework',
          '${SDKROOT}/System/Library/Frameworks/MessageUI.framework',
          '${SDKROOT}/System/Library/Frameworks/MobileCoreServices.framework',
          '${SDKROOT}/System/Library/Frameworks/MultipeerConnectivity.framework',
          '${SDKROOT}/System/Library/Frameworks/OpenGLES.framework',
          '${SDKROOT}/System/Library/Frameworks/QuartzCore.framework',
          '${SDKROOT}/System/Library/Frameworks/Security.framework',
          '${SDKROOT}/System/Library/Frameworks/StoreKit.framework',
          '${SDKROOT}/System/Library/Frameworks/SystemConfiguration.framework',
          '${SDKROOT}/System/Library/Frameworks/UIKit.framework',
        ],
      },
      'sources': [
        '${INTERMEDIATE_DIR}/DeveloperDefines.h',
        '${INTERMEDIATE_DIR}/TestDefines.h',


        '<!@(ls Source/*.cc)',
        '<!@(ls Source/*.mm)',
        '<!@(ls Source/*.m)',
        '<!@(ls Source/Tests/*.mm)',
        '<!@(ls Source/Tests/*.m)',
        '<!@(ls Source/Tests/*.cc)',
      ],
      'mac_bundle_resources': [
        'third_party_shared/icudata/icudt51l.dat',
        '${INTERMEDIATE_DIR}/Viewfinder-Version.plist',

        # TODO(ben): move test-photo.jpg somewhere else.
        '<!@(ls Source/Images/*.jpg | fgrep -v test-photo.jpg)',

        '<!@(ls Source/Fonts/*.ttf)',
        '<!@(ls Source/Images/*.png)',
        '<!@(ls Source/Curves/*.png)',
        '<!@(ls Source/Shaders/*.fsh)',
        '<!@(ls Source/Shaders/*.vsh)',
      ],
    },
  ],
}
