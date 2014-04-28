# Based on http://src.chromium.org/svn/trunk/src/build/protoc.gypi
#
# Include this rule in a library or executable target to generate the
# c++ code for all .proto files listed in 'sources'.
{
  'conditions': [
    ['OS=="ios"', {
      'variables': {
        'protoc_wrapper%': '<(DEPTH)/../shared/scripts/protoc-gyp.sh',
      },
      'all_dependent_settings': {
        'include_dirs': [
          '${SHARED_INTERMEDIATE_DIR}/protoc_out',
        ],
      },
    },],
    ['OS=="android"', {
      'variables': {
        'protoc_wrapper%': '<(DEPTH)/clients/shared/scripts/protoc-gyp.sh',
      },
      'all_dependent_settings': {
        'include_dirs': [
          # HACK: on android $SHARED_INTERMEDIATE_DIR is not actually shared, and will be evaluated
          # in the context of the dependent target.  We must use an explicitly relative path here
          # so it will be resolved correctly.
          './protoc_out',
        ],
      },
    },],
  ],
  'variables': {
    'proto_out_dir%': '',
  },
  'rules': [
    {
      'rule_name': 'genproto',
      'extension': 'proto',
      'inputs': [
        '<(protoc_wrapper)',
      ],
      'outputs': [
        '<(SHARED_INTERMEDIATE_DIR)/protoc_out/<(proto_out_dir)<(RULE_INPUT_ROOT).pb.cc',
        '<(SHARED_INTERMEDIATE_DIR)/protoc_out/<(proto_out_dir)<(RULE_INPUT_ROOT).pb.h',
      ],
      'action': [
        'bash',
        '<(protoc_wrapper)',
        '>(_include_dirs)',
        '<(RULE_INPUT_PATH)',
        '<(SHARED_INTERMEDIATE_DIR)/protoc_out/<(proto_out_dir)'
      ],
      'message': 'Generating C++ code from <(RULE_INPUT_PATH)',
      'process_outputs_as_sources': 1,
    },
  ],
  'include_dirs': [
    '${SHARED_INTERMEDIATE_DIR}/protoc_out',
  ],
  # This target exports a hard dependency because it generates header files.
  'hard_dependency': 1,
}
