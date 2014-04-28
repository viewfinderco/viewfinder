// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_EXIF_H
#define VIEWFINDER_EXIF_H

#include "Utils.h"
#include "WallTime.h"

class DataSource {
 public:
  DataSource()
      : n_(0) {
  }
  virtual ~DataSource() {
  }

  Slice Peek() {
    if (s_.empty()) {
      if (n_ > 0) {
        AdvanceInternal(n_);
      }
      s_ = PeekInternal();
      n_ = s_.size();
    }
    return s_;
  }

  void Advance(int n) {
    const int t = std::min<int>(n, s_.size());
    s_.remove_prefix(t);
    if (s_.empty()) {
      n_ += (n - t);
    }
  }

 protected:
  virtual Slice PeekInternal() = 0;
  virtual void AdvanceInternal(int n) = 0;

 private:
  Slice s_;
  int n_;
};

class SliceDataSource : public DataSource {
 public:
  SliceDataSource(const Slice& s)
      : str_(s) {
  }

 protected:
  Slice PeekInternal() {
    return str_;
  }
  void AdvanceInternal(int n) {
    str_.remove_prefix(n);
  }

 private:
  Slice str_;
};

enum ExifTag {
  kExifImageWidth = 0x0100,
  kExifImageLength = 0x0101,
  kExifBitsPerSample = 0x0102,
  kExifCompression = 0x0103,
  kExifPhotometricInterpretation = 0x0106,
  kExifImageDescription = 0x010e,
  kExifMake = 0x010f,
  kExifModel = 0x0110,
  kExifStripOffsets = 0x0111,
  kExifOrientation = 0x0112,
  kExifSamplesPerPixel = 0x0115,
  kExifRowsPerStrip = 0x0116,
  kExifStripByteCounts = 0x0117,
  kExifXResolution = 0x011a,
  kExifYResolution = 0x011b,
  kExifPlanarConfiguration = 0x011c,
  kExifResolutionUnit = 0x0128,
  kExifSoftware = 0x0131,
  kExifDateTime = 0x0132,
  kExifArtist = 0x013b,
  kExifHostComputer = 0x013c,
  kExifPredictor = 0x013d,
  kExifWhitePoint = 0x013e,
  kExifPrimaryChromaticities = 0x013f,
  kExifJPEGInterchangeFormat = 0x0201,
  kExifJPEGInterchangeFormatLength = 0x0202,
  kExifYCbCrCoefficients = 0x0211,
  kExifYCbCrSubSampling = 0x0212,
  kExifYCbCrPositioning = 0x0213,
  kExifReferenceBlackWhite = 0x0214,
  kExifCopyright = 0x8298,
  kExifExif = 0x8769,
  kExifGPS = 0x8825,
  kExifSpectralSensitivity = 0x8824,
  kExifExposureProgram = 0x8822,
  kExifISOSpeedratings = 0x8827,
  kExifExposureTime = 0x829a,
  kExifFNumber = 0x829d,
  kExifExifVersion = 0x9000,
  kExifDateTimeOriginal = 0x9003,
  kExifDateTimeDigitized = 0x9004,
  kExifComponentsConfiguration = 0x9101,
  kExifCompressedBitsPerPixel = 0x9102,
  kExifShutterSpeedValue = 0x9201,
  kExifApertureValue = 0x9202,
  kExifBrightnessValue = 0x9203,
  kExifExposureBiasValue = 0x9204,
  kExifMaxApertureRatioValue = 0x9205,
  kExifSubjectDistance = 0x9206,
  kExifMeteringMode = 0x9207,
  kExifLightSource = 0x9208,
  kExifFlash = 0x9209,
  kExifFocalLength = 0x920a,
  kExifMakerNote = 0x927c,
  kExifUserComment = 0x9286,
  kExifSubSecTime = 0x9290,
  kExifSubSecTimeOriginal = 0x9291,
  kExifSubSecTimeDigitized = 0x9292,
  kExifFileSource = 0xa300,
  kExifSceneType = 0xa301,
  kExifCFAPattern = 0xa302,
  kExifFlashpixVersion = 0xa000,
  kExifColorSpace = 0xa001,
  kExifPixelXDimension = 0xa002,
  kExifPixelYDimension = 0xa003,
  kExifInterop = 0xa005,
  kExifFocalPlaneXResolution = 0xa20e,
  kExifFocalPlaneYResolution = 0xa20f,
  kExifFocalPlaneResolutionUnit = 0xa210,
  kExifSubjectLocation = 0xa214,
  kExifExposureIndex = 0xa215,
  kExifSensingMethod = 0xa217,
  kExifCustomRendered = 0xa401,
  kExifExposureMode = 0xa402,
  kExifWhiteBalance = 0xa403,
  kExifDigitalZoomRatio = 0xa404,
  kExifFocalLengthIn35mmFilm = 0xa405,
  kExifSceneCaptureType = 0xa406,
  kExifGainControl = 0xa407,
  kExifContrast = 0xa408,
  kExifSaturation = 0xa409,
  kExifSharpness = 0xa40a,
  kExifDeviceSettingDescription = 0xa40b,
  kExifSubjectDistanceRange = 0xa40c,
  kExifGamma = 0xa500,
  kExifGPSVersion = 0x0000,
  kExifGPSLatitudeRef = 0x0001,
  kExifGPSLatitude = 0x0002,
  kExifGPSLongitudeRef = 0x0003,
  kExifGPSLongitude = 0x0004,
  kExifGPSAltitudeRef = 0x0005,
  kExifGPSAltitude = 0x0006,
  kExifGPSTimeStamp = 0x0007,
  kExifGPSSatellites = 0x0008,
  kExifGPSStatus = 0x0009,
  kExifGPSMeasureMode = 0x000a,
  kExifGPSDOP = 0x000b,
  kExifGPSSpeedRef = 0x000c,
  kExifGPSSpeed = 0x000d,
  kExifGPSTrackRef = 0x000e,
  kExifGPSTrack = 0x000f,
  kExifGPSImgDirectionRef = 0x0010,
  kExifGPSImgDirection = 0x0011,
  kExifGPSMapDatum = 0x0012,
  kExifGPSDestLatitudeRef = 0x0013,
  kExifGPSDestLatitude = 0x0014,
  kExifGPSDestLongitudeRef = 0x0015,
  kExifGPSDestLongitude = 0x0016,
  kExifGPSDestBearingRef = 0x0017,
  kExifGPSDestBearing = 0x0018,
  kExifGPSDestDistanceRef = 0x0019,
  kExifGPSDestDistance = 0x001a,
};

enum ExifFormat {
  kExifFormatByte = 1,
  kExifFormatString = 2,
  kExifFormatUshort = 3,
  kExifFormatUlong = 4,
  kExifFormatUrational = 5,
  kExifFormatSbyte = 6,
  kExifFormatUndefined = 7,
  kExifFormatSshort = 8,
  kExifFormatSlong = 9,
  kExifFormatSrational = 10,
  kExifFormatSingle = 11,
  kExifFormatDouble = 12,
};

typedef void (^TagCallback)(ExifTag tag, ExifFormat format, const Slice& data);

bool ScanExif(Slice s, TagCallback callback);
bool ScanJpeg(DataSource* s, TagCallback callback);
bool ScanJpeg(Slice s, TagCallback callback);

WallTime ParseExifDate(const Slice& s);

#endif  // VIEWFINDER_EXIF_H
