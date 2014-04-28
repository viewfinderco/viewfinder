#include <stdio.h>
#include <Python.h>
#include <CoreGraphics/CGDataProvider.h>
#include <ImageIO/ImageIO.h>
#include "ImageFingerprint.h"

using std::string;
using std::vector;

static PyObject* PyFingerprintImage(PyObject* self, PyObject* args) {
  char* filename;
  if (!PyArg_ParseTuple(args, "s", &filename)) {
    return NULL;
  }

  CGDataProviderRef provider = CGDataProviderCreateWithFilename(filename);
  if (!provider) {
    PyErr_SetString(PyExc_Exception, "error creating CGDataProvider");
    return NULL;
  }
  CGImageSourceRef source = CGImageSourceCreateWithDataProvider(provider, NULL);
  if (!source) {
    CFRelease(provider);
    PyErr_SetString(PyExc_Exception, "error creating CGImageSource");
    return NULL;
  }
  CGImageRef image = CGImageSourceCreateImageAtIndex(source, 0, NULL);
  if (!image) {
    CFRelease(source);
    CFRelease(provider);
    PyErr_SetString(PyExc_Exception, "error creating CGImage");
    return NULL;
  }

  vector<string> fingerprint = FingerprintImage(image);

  CFRelease(image);
  CFRelease(source);
  CFRelease(provider);

  PyObject* list = PyList_New(fingerprint.size());
  for (int i = 0; i < fingerprint.size(); i++) {
    PyList_SET_ITEM(list, i, PyString_FromStringAndSize(fingerprint[i].data(),
                                                        fingerprint[i].size()));
  }

  return list;
};

static PyMethodDef kMethods[] = {
  {"FingerprintImage", PyFingerprintImage, METH_VARARGS, ""},
  {NULL, NULL, 0, NULL},
};

PyMODINIT_FUNC initimagefingerprint(void) {
  Py_InitModule("imagefingerprint", kMethods);
}
