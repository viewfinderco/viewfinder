#!/bin/bash

if test "${PLATFORM_NAME}" = "iphonesimulator"; then
  # TODO(ben): move this to Source/Images-Simulator/ once we've moved to gyp.
  cp Source/Images/test-photo.jpg ${BUILT_PRODUCTS_DIR}/${FULL_PRODUCT_NAME}/
fi
