// Copyright 2026 The I.K.E. Browser authors
// SPDX-License-Identifier: BSD-3-Clause
//
// Test tool, never shipped. Drives the H.264 and AAC decoders that are part of
// Windows with the same Media Foundation calls, in the same order, as the
// engine patches do (patches/chromium/0003 and 0004), but without Chromium:
// it builds in seconds, so what Windows answers to those calls is known long
// before a build of the engine is finished.
//
//   mft_probe h264 STREAM.h264 PTS.txt WIDTH HEIGHT [low-delay]
//       STREAM.h264: Annex B, every picture starting with an access unit
//       delimiter; PTS.txt: one presentation time in seconds per picture, in
//       the order of the stream. The pictures are four coloured quarters:
//       red, green / blue, white.
//   mft_probe aac SOUND.aac raw|adts
//       SOUND.aac: AAC frames with ADTS headers. "raw" hands the decoder bare
//       frames and an AudioSpecificConfig (as from an MP4 file); "adts" hands
//       it the frames with their headers (as from Media Source).
//
// Like the engine: no COM initialisation, the decoders are created with
// DllGetClassObject from libraries loaded from the system directory, and the
// H.264 part never calls MFStartup (the renderer does not).

#define NOMINMAX
#include <windows.h>

#include <mfapi.h>
#include <mferror.h>
#include <mfidl.h>
#include <mfobjects.h>
#include <mftransform.h>
#include <mmreg.h>
#include <wrl/client.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;

namespace {

const GUID kH264DecoderClsid = {0x62ce7e72, 0x4c71, 0x4d20,
                                {0xb1, 0x5d, 0x45, 0x28, 0x31, 0xa8, 0x7d, 0x9d}};
const GUID kAacDecoderClsid = {0x32d186a7, 0x218f, 0x4c75,
                               {0x88, 0x76, 0xdd, 0x77, 0x27, 0x3a, 0x89, 0x99}};
const GUID kLowLatencyMode = {0x9c27891a, 0xed7a, 0x40e1,
                              {0x88, 0xe8, 0xb2, 0x27, 0x27, 0xa0, 0x24, 0xee}};

int g_failures = 0;

void Fail(const char* what, HRESULT hr = S_OK) {
  ++g_failures;
  if (hr != S_OK) {
    printf("FAIL: %s (0x%08lX)\n", what, static_cast<unsigned long>(hr));
  } else {
    printf("FAIL: %s\n", what);
  }
  fflush(stdout);
}

#define CHECK_HR(hr, what)        \
  do {                            \
    HRESULT hr_ = (hr);           \
    if (FAILED(hr_)) {            \
      Fail(what, hr_);            \
      return false;               \
    }                             \
  } while (0)

std::vector<uint8_t> ReadFile(const char* path) {
  std::vector<uint8_t> data;
  FILE* file = nullptr;
  if (fopen_s(&file, path, "rb") != 0 || !file) {
    return data;
  }
  fseek(file, 0, SEEK_END);
  long size = ftell(file);
  fseek(file, 0, SEEK_SET);
  if (size > 0) {
    data.resize(static_cast<size_t>(size));
    if (fread(data.data(), 1, data.size(), file) != data.size()) {
      data.clear();
    }
  }
  fclose(file);
  return data;
}

ComPtr<IMFTransform> CreateFromLibrary(const wchar_t* library_name,
                                       const GUID& clsid) {
  HMODULE library =
      ::LoadLibraryExW(library_name, nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
  if (!library) {
    printf("  %ls: not loaded, error %lu\n", library_name, ::GetLastError());
    return nullptr;
  }
  using Function = HRESULT(STDAPICALLTYPE*)(REFCLSID, REFIID, LPVOID*);
  auto get_class_object =
      reinterpret_cast<Function>(::GetProcAddress(library, "DllGetClassObject"));
  if (!get_class_object) {
    printf("  %ls: no DllGetClassObject\n", library_name);
    return nullptr;
  }
  ComPtr<IClassFactory> factory;
  HRESULT hr = get_class_object(clsid, IID_PPV_ARGS(&factory));
  if (FAILED(hr) || !factory) {
    printf("  %ls: no class factory (0x%08lX)\n", library_name,
           static_cast<unsigned long>(hr));
    return nullptr;
  }
  ComPtr<IMFTransform> transform;
  hr = factory->CreateInstance(nullptr, IID_PPV_ARGS(&transform));
  if (FAILED(hr) || !transform) {
    printf("  %ls: CreateInstance failed (0x%08lX)\n", library_name,
           static_cast<unsigned long>(hr));
    return nullptr;
  }
  return transform;
}

// As CreateEmptySampleWithBuffer() in Chromium's media/base/win/mf_helpers.cc.
ComPtr<IMFSample> CreateSample(uint32_t length, int align) {
  ComPtr<IMFSample> sample;
  if (FAILED(MFCreateSample(&sample))) {
    return nullptr;
  }
  ComPtr<IMFMediaBuffer> buffer;
  HRESULT hr = align == 0
                   ? MFCreateMemoryBuffer(length, &buffer)
                   : MFCreateAlignedMemoryBuffer(length, align - 1, &buffer);
  if (FAILED(hr) || FAILED(sample->AddBuffer(buffer.Get()))) {
    return nullptr;
  }
  buffer->SetCurrentLength(0);
  return sample;
}

bool FillSample(IMFSample* sample, const uint8_t* data, size_t size) {
  ComPtr<IMFMediaBuffer> buffer;
  CHECK_HR(sample->GetBufferByIndex(0, &buffer), "GetBufferByIndex");
  uint8_t* destination = nullptr;
  DWORD max_length = 0;
  CHECK_HR(buffer->Lock(&destination, &max_length, nullptr), "Lock input");
  if (size <= max_length) {
    memcpy(destination, data, size);
  }
  buffer->Unlock();
  if (size > max_length) {
    Fail("input does not fit its buffer");
    return false;
  }
  CHECK_HR(buffer->SetCurrentLength(static_cast<DWORD>(size)),
           "SetCurrentLength");
  return true;
}

// --- H.264 -------------------------------------------------------------------

struct Yuv {
  int y, u, v;
};

class H264Probe {
 public:
  bool Create(int width, int height, bool low_delay) {
    coded_width_ = width;
    coded_height_ = height;
    transform_ = CreateFromLibrary(L"msmpeg2vdec.dll", kH264DecoderClsid);
    if (!transform_) {
      Fail("the H.264 decoder of Windows could not be created");
      return false;
    }
    if (low_delay) {
      ComPtr<IMFAttributes> attributes;
      if (SUCCEEDED(transform_->GetAttributes(&attributes)) && attributes) {
        HRESULT hr = attributes->SetUINT32(kLowLatencyMode, TRUE);
        printf("  low latency mode: 0x%08lX\n", static_cast<unsigned long>(hr));
      }
    }
    ComPtr<IMFMediaType> input_type;
    CHECK_HR(MFCreateMediaType(&input_type), "MFCreateMediaType");
    CHECK_HR(input_type->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video), "major");
    CHECK_HR(input_type->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_H264), "subtype");
    CHECK_HR(input_type->SetUINT32(MF_MT_INTERLACE_MODE,
                                   MFVideoInterlace_MixedInterlaceOrProgressive),
             "interlace mode");
    CHECK_HR(MFSetAttributeSize(input_type.Get(), MF_MT_FRAME_SIZE, width,
                                height),
             "frame size");
    CHECK_HR(transform_->SetInputType(0, input_type.Get(), 0), "SetInputType");
    if (!ConfigureOutput()) {
      return false;
    }
    HRESULT hr =
        transform_->ProcessMessage(MFT_MESSAGE_NOTIFY_BEGIN_STREAMING, 0);
    printf("  NOTIFY_BEGIN_STREAMING: 0x%08lX\n", static_cast<unsigned long>(hr));
    hr = transform_->ProcessMessage(MFT_MESSAGE_NOTIFY_START_OF_STREAM, 0);
    printf("  NOTIFY_START_OF_STREAM: 0x%08lX\n", static_cast<unsigned long>(hr));
    return true;
  }

  bool ConfigureOutput() {
    ComPtr<IMFMediaType> output_type;
    for (DWORD index = 0;; ++index) {
      output_type.Reset();
      HRESULT hr = transform_->GetOutputAvailableType(0, index, &output_type);
      if (FAILED(hr)) {
        Fail("no YV12 among the output types", hr);
        return false;
      }
      GUID subtype = GUID_NULL;
      if (SUCCEEDED(output_type->GetGUID(MF_MT_SUBTYPE, &subtype)) &&
          subtype == MFVideoFormat_YV12) {
        break;
      }
    }
    CHECK_HR(transform_->SetOutputType(0, output_type.Get(), 0),
             "SetOutputType");
    UINT32 width = 0, height = 0;
    CHECK_HR(MFGetAttributeSize(output_type.Get(), MF_MT_FRAME_SIZE, &width,
                                &height),
             "output frame size");
    width_ = static_cast<int>(width);
    height_ = static_cast<int>(height);
    UINT32 default_stride = 0;
    HRESULT stride_hr =
        output_type->GetUINT32(MF_MT_DEFAULT_STRIDE, &default_stride);
    stride_ = (SUCCEEDED(stride_hr) &&
               static_cast<int32_t>(default_stride) >= width_)
                  ? static_cast<int>(default_stride)
                  : width_;
    MFVideoArea area = {};
    UINT32 blob_size = 0;
    has_aperture_ = SUCCEEDED(output_type->GetBlob(
                        MF_MT_MINIMUM_DISPLAY_APERTURE,
                        reinterpret_cast<UINT8*>(&area), sizeof(area),
                        &blob_size)) &&
                    blob_size == sizeof(area);
    if (has_aperture_) {
      visible_width_ = area.Area.cx;
      visible_height_ = area.Area.cy;
    } else {
      visible_width_ = std::min(coded_width_, width_);
      visible_height_ = std::min(coded_height_, height_);
    }
    MFT_OUTPUT_STREAM_INFO info = {};
    CHECK_HR(transform_->GetOutputStreamInfo(0, &info), "GetOutputStreamInfo");
    transform_allocates_ =
        (info.dwFlags & (MFT_OUTPUT_STREAM_PROVIDES_SAMPLES |
                         MFT_OUTPUT_STREAM_CAN_PROVIDE_SAMPLES)) != 0;
    printf("  output: YV12 %dx%d, default stride %s%d, aperture %s %dx%d, "
           "stream flags 0x%lX, cbSize %lu, cbAlignment %lu, transform "
           "allocates: %s\n",
           width_, height_, SUCCEEDED(stride_hr) ? "" : "(absent) ", stride_,
           has_aperture_ ? "yes" : "no", visible_width_, visible_height_,
           info.dwFlags, info.cbSize, info.cbAlignment,
           transform_allocates_ ? "yes" : "no");
    output_sample_.Reset();
    if (!transform_allocates_) {
      if (info.cbSize == 0) {
        Fail("empty output buffer size");
        return false;
      }
      output_sample_ = CreateSample(info.cbSize, static_cast<int>(info.cbAlignment));
      if (!output_sample_) {
        Fail("could not create the output sample");
        return false;
      }
    }
    return true;
  }

  bool Decode(const std::vector<uint8_t>& unit, LONGLONG time) {
    ComPtr<IMFSample> sample = CreateSample(static_cast<uint32_t>(unit.size()), 0);
    if (!sample || !FillSample(sample.Get(), unit.data(), unit.size())) {
      Fail("could not create an input sample");
      return false;
    }
    CHECK_HR(sample->SetSampleTime(time), "SetSampleTime");
    HRESULT hr = transform_->ProcessInput(0, sample.Get(), 0);
    if (hr == MF_E_NOTACCEPTING) {
      ++not_accepting_;
      if (!Pump()) {
        return false;
      }
      hr = transform_->ProcessInput(0, sample.Get(), 0);
    }
    CHECK_HR(hr, "ProcessInput");
    return Pump();
  }

  bool Drain() {
    CHECK_HR(transform_->ProcessMessage(MFT_MESSAGE_COMMAND_DRAIN, 0), "DRAIN");
    return Pump();
  }

  bool Flush() {
    CHECK_HR(transform_->ProcessMessage(MFT_MESSAGE_COMMAND_FLUSH, 0), "FLUSH");
    return true;
  }

  bool Pump() {
    int changes = 0;
    for (;;) {
      MFT_OUTPUT_DATA_BUFFER output = {};
      output.pSample = output_sample_.Get();
      DWORD status = 0;
      HRESULT hr = transform_->ProcessOutput(0, 1, &output, &status);
      if (output.pEvents) {
        output.pEvents->Release();
      }
      ComPtr<IMFSample> transform_sample;
      if (!output_sample_ && output.pSample) {
        transform_sample.Attach(output.pSample);
      }
      if (hr == MF_E_TRANSFORM_NEED_MORE_INPUT) {
        return true;
      }
      if (hr == MF_E_TRANSFORM_STREAM_CHANGE) {
        ++stream_changes_;
        printf("  stream change after %zu pictures\n", times.size());
        if (++changes > 64 || !ConfigureOutput()) {
          Fail("stream change not handled");
          return false;
        }
        continue;
      }
      CHECK_HR(hr, "ProcessOutput");
      if (!output.pSample) {
        Fail("ProcessOutput gave no sample");
        return false;
      }
      if (!Deliver(output.pSample)) {
        return false;
      }
      if (output_sample_) {
        ComPtr<IMFMediaBuffer> buffer;
        if (SUCCEEDED(output_sample_->GetBufferByIndex(0, &buffer))) {
          buffer->SetCurrentLength(0);
        }
      }
    }
  }

  bool Deliver(IMFSample* sample) {
    LONGLONG time = 0;
    CHECK_HR(sample->GetSampleTime(&time), "GetSampleTime");
    ComPtr<IMFMediaBuffer> buffer;
    CHECK_HR(sample->ConvertToContiguousBuffer(&buffer),
             "ConvertToContiguousBuffer");
    uint8_t* data = nullptr;
    DWORD size = 0;
    CHECK_HR(buffer->Lock(&data, nullptr, &size), "Lock output");
    // The same search as MediaFoundationVideoDecoder::DeliverFrame().
    const int64_t strides[] = {stride_, (stride_ + 15) & ~15, width_,
                               (width_ + 15) & ~15};
    const int64_t row_counts[] = {(height_ + 15) & ~15, height_};
    bool found = false;
    int64_t stride = 0, rows = 0;
    int pass_used = 0;
    for (int pass = 0; pass < 2 && !found; ++pass) {
      for (int64_t r : row_counts) {
        for (int64_t s : strides) {
          if (s < width_ || s % 2 || r < height_ || r % 2) {
            continue;
          }
          const int64_t needed = s * r * 3 / 2;
          if (pass == 0 ? needed == size : needed <= size) {
            stride = s;
            rows = r;
            found = true;
            pass_used = pass;
            break;
          }
        }
        if (found) {
          break;
        }
      }
    }
    bool ok = true;
    if (!found) {
      printf("  picture of %lu bytes fits no layout of %dx%d stride %d\n", size,
             width_, height_, stride_);
      Fail("unexpected picture layout");
      ok = false;
    } else {
      if (times.empty() || stride != last_stride_ || rows != last_rows_) {
        printf("  picture layout: %lu bytes = stride %lld x rows %lld x 3/2 "
               "(%s match)\n",
               size, stride, rows, pass_used == 0 ? "exact" : "loose");
        last_stride_ = stride;
        last_rows_ = rows;
        if (pass_used != 0) {
          ++loose_layouts_;
        }
      }
      const uint8_t* y_plane = data;
      const uint8_t* v_plane = data + stride * rows;
      const uint8_t* u_plane = v_plane + (stride / 2) * (rows / 2);
      // Centres of the four quarters of the shown picture.
      const int xs[] = {visible_width_ / 4, visible_width_ * 3 / 4};
      const int ys[] = {visible_height_ / 4, visible_height_ * 3 / 4};
      Yuv quarters[4];
      for (int q = 0; q < 4; ++q) {
        const int x = xs[q % 2], y = ys[q / 2];
        quarters[q].y = y_plane[y * stride + x];
        quarters[q].u = u_plane[(y / 2) * (stride / 2) + x / 2];
        quarters[q].v = v_plane[(y / 2) * (stride / 2) + x / 2];
      }
      // Red, green, blue, white in limited-range BT.601.
      const Yuv wanted[4] = {{81, 90, 240}, {145, 54, 34}, {41, 240, 110},
                             {235, 128, 128}};
      for (int q = 0; q < 4; ++q) {
        if (abs(quarters[q].y - wanted[q].y) > 14 ||
            abs(quarters[q].u - wanted[q].u) > 14 ||
            abs(quarters[q].v - wanted[q].v) > 14) {
          if (wrong_colours_ == 0) {
            printf("  picture %zu, quarter %d: Y %d U %d V %d, wanted %d %d %d\n",
                   times.size(), q, quarters[q].y, quarters[q].u, quarters[q].v,
                   wanted[q].y, wanted[q].u, wanted[q].v);
          }
          ++wrong_colours_;
        }
      }
      if (times.empty()) {
        printf("  first picture, quarters (Y U V): %d %d %d | %d %d %d | "
               "%d %d %d | %d %d %d\n",
               quarters[0].y, quarters[0].u, quarters[0].v, quarters[1].y,
               quarters[1].u, quarters[1].v, quarters[2].y, quarters[2].u,
               quarters[2].v, quarters[3].y, quarters[3].u, quarters[3].v);
      }
    }
    buffer->Unlock();
    times.push_back(time);
    return ok;
  }

  std::vector<LONGLONG> times;
  int stream_changes_ = 0;
  int not_accepting_ = 0;
  int wrong_colours_ = 0;
  int loose_layouts_ = 0;

 private:
  ComPtr<IMFTransform> transform_;
  ComPtr<IMFSample> output_sample_;
  bool transform_allocates_ = false;
  bool has_aperture_ = false;
  int coded_width_ = 0, coded_height_ = 0;
  int width_ = 0, height_ = 0, stride_ = 0;
  int visible_width_ = 0, visible_height_ = 0;
  int64_t last_stride_ = 0, last_rows_ = 0;
};

// Splits an Annex B stream into pictures at the access unit delimiters and
// leaves the delimiters out: the engine's demuxers deliver none.
std::vector<std::vector<uint8_t>> SplitAccessUnits(
    const std::vector<uint8_t>& stream) {
  std::vector<size_t> starts;  // offset of each start code's 00 00 01
  for (size_t i = 0; i + 3 < stream.size(); ++i) {
    if (stream[i] == 0 && stream[i + 1] == 0 && stream[i + 2] == 1) {
      starts.push_back(i);
      i += 2;
    }
  }
  std::vector<std::vector<uint8_t>> units;
  for (size_t n = 0; n < starts.size(); ++n) {
    const size_t payload = starts[n] + 3;
    size_t end = n + 1 < starts.size() ? starts[n + 1] : stream.size();
    // A four-byte start code of the next unit begins one byte earlier.
    if (n + 1 < starts.size() && end > payload && stream[end - 1] == 0) {
      --end;
    }
    if (payload >= end) {
      continue;
    }
    const int type = stream[payload] & 0x1F;
    if (type == 9) {
      units.emplace_back();
      continue;
    }
    if (units.empty()) {
      units.emplace_back();
    }
    static const uint8_t kStartCode[] = {0, 0, 0, 1};
    auto& unit = units.back();
    unit.insert(unit.end(), kStartCode, kStartCode + 4);
    unit.insert(unit.end(), stream.begin() + payload, stream.begin() + end);
  }
  units.erase(std::remove_if(units.begin(), units.end(),
                             [](const std::vector<uint8_t>& u) {
                               return u.empty();
                             }),
              units.end());
  return units;
}

int RunH264(int argc, char** argv) {
  if (argc < 6) {
    return 2;
  }
  const std::vector<uint8_t> stream = ReadFile(argv[2]);
  const int width = atoi(argv[4]);
  const int height = atoi(argv[5]);
  const bool low_delay = argc > 6 && strcmp(argv[6], "low-delay") == 0;
  std::vector<LONGLONG> pts;
  {
    FILE* file = nullptr;
    if (fopen_s(&file, argv[3], "r") == 0 && file) {
      char line[128];
      while (fgets(line, sizeof(line), file)) {
        char* end = nullptr;
        const double seconds = strtod(line, &end);
        if (end != line) {
          pts.push_back(static_cast<LONGLONG>(llround(seconds * 1e7)));
        }
      }
      fclose(file);
    }
  }
  const auto units = SplitAccessUnits(stream);
  printf("H.264 %s: %zu bytes, %zu pictures, %zu times, %dx%d%s\n", argv[2],
         stream.size(), units.size(), pts.size(), width, height,
         low_delay ? ", low delay" : "");
  if (units.empty() || units.size() != pts.size()) {
    Fail("the stream and the list of times do not match");
    return 1;
  }

  H264Probe probe;
  if (!probe.Create(width, height, low_delay)) {
    return 1;
  }
  size_t first_output_after = 0;
  for (size_t i = 0; i < units.size(); ++i) {
    if (!probe.Decode(units[i], pts[i])) {
      printf("  failed at picture %zu\n", i);
      return 1;
    }
    if (first_output_after == 0 && !probe.times.empty()) {
      first_output_after = i + 1;
    }
  }
  const size_t before_drain = probe.times.size();
  if (!probe.Drain()) {
    return 1;
  }
  printf("  pictures out: %zu of %zu (%zu before the drain; first one after "
         "%zu inputs); stream changes %d; not-accepting %d\n",
         probe.times.size(), units.size(), before_drain, first_output_after,
         probe.stream_changes_, probe.not_accepting_);
  if (probe.times.size() != units.size()) {
    Fail("not every picture came out");
  }
  std::vector<LONGLONG> sorted = pts;
  std::sort(sorted.begin(), sorted.end());
  if (probe.times != sorted) {
    Fail("the pictures did not come out in presentation order with the "
         "times that went in");
    for (size_t i = 0; i < probe.times.size() && i < 12; ++i) {
      printf("    out %lld, wanted %lld\n", probe.times[i],
             i < sorted.size() ? sorted[i] : -1);
    }
  }
  if (probe.wrong_colours_) {
    printf("  quarters with wrong colours: %d\n", probe.wrong_colours_);
    Fail("wrong colours");
  }
  if (probe.loose_layouts_) {
    printf("  NOTE: a picture layout was only matched loosely\n");
  }

  // As after a seek: flush, then decode again from the first key frame.
  const size_t before = probe.times.size();
  const size_t again = std::min<size_t>(units.size(), 30);
  if (!probe.Flush()) {
    return 1;
  }
  for (size_t i = 0; i < again; ++i) {
    if (!probe.Decode(units[i], pts[i])) {
      printf("  after flush: failed at picture %zu\n", i);
      return 1;
    }
  }
  if (!probe.Drain()) {
    return 1;
  }
  printf("  after flush: %zu pictures out of %zu\n", probe.times.size() - before,
         again);
  if (probe.times.size() - before != again) {
    Fail("after a flush not every picture came out");
  }
  // And once more without a drain in between, as a seek in mid-stream.
  const size_t before2 = probe.times.size();
  for (size_t i = 0; i < again / 2; ++i) {
    if (!probe.Decode(units[i], pts[i])) {
      return 1;
    }
  }
  if (!probe.Flush()) {
    return 1;
  }
  const size_t before3 = probe.times.size();
  for (size_t i = 0; i < again; ++i) {
    if (!probe.Decode(units[i], pts[i])) {
      printf("  after mid-stream flush: failed at picture %zu\n", i);
      return 1;
    }
  }
  if (!probe.Drain()) {
    return 1;
  }
  printf("  mid-stream flush: %zu pictures before it, %zu of %zu after it\n",
         before3 - before2, probe.times.size() - before3, again);
  if (probe.times.size() - before3 != again) {
    Fail("after a mid-stream flush not every picture came out");
  }
  return g_failures ? 1 : 0;
}

// --- AAC ---------------------------------------------------------------------

struct AdtsFrame {
  size_t offset;
  size_t header_size;
  size_t size;
};

class AacProbe {
 public:
  bool Create(int object_type, int frequency_index, int sample_rate,
              int channels, bool adts) {
    transform_ = CreateFromLibrary(L"msauddecmft.dll", kAacDecoderClsid);
    if (!transform_) {
      Fail("the AAC decoder of Windows could not be created");
      return false;
    }
    // As GetAacAudioType() in Chromium's mf_helpers.cc, with the change of
    // patch 0004 for frames that keep their ADTS header.
    std::vector<uint8_t> extra_data;
    if (!adts) {
      extra_data.push_back(
          static_cast<uint8_t>((object_type << 3) | (frequency_index >> 1)));
      extra_data.push_back(
          static_cast<uint8_t>(((frequency_index & 1) << 7) | (channels << 3)));
    }
    ComPtr<IMFMediaType> type;
    CHECK_HR(MFCreateMediaType(&type), "MFCreateMediaType");
    CHECK_HR(type->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Audio), "major");
    CHECK_HR(type->SetGUID(MF_MT_SUBTYPE, MFAudioFormat_AAC), "subtype");
    CHECK_HR(type->SetUINT32(MF_MT_COMPRESSED, 1), "compressed");
    CHECK_HR(type->SetUINT32(MF_MT_AUDIO_NUM_CHANNELS, channels), "channels");
    CHECK_HR(type->SetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, sample_rate),
             "sample rate");
    CHECK_HR(type->SetUINT32(MF_MT_AUDIO_BITS_PER_SAMPLE, 16), "bits");
    std::vector<uint8_t> format(sizeof(HEAACWAVEINFO) + extra_data.size());
    auto* wave = reinterpret_cast<HEAACWAVEINFO*>(format.data());
    wave->wfx.wFormatTag = WAVE_FORMAT_MPEG_HEAAC;
    wave->wfx.nChannels = static_cast<WORD>(channels);
    wave->wfx.wBitsPerSample = 16;
    wave->wfx.nSamplesPerSec = sample_rate;
    wave->wfx.nAvgBytesPerSec = sample_rate * channels * 2;
    wave->wfx.nBlockAlign = 1;
    wave->wfx.cbSize = static_cast<WORD>(format.size() - sizeof(WAVEFORMATEX));
    wave->wPayloadType = 0;
    wave->wAudioProfileLevelIndication = 0xFE;
    wave->wStructType = 0;
    if (!extra_data.empty()) {
      memcpy(format.data() + sizeof(HEAACWAVEINFO), extra_data.data(),
             extra_data.size());
    }
    CHECK_HR(MFInitMediaTypeFromWaveFormatEx(
                 type.Get(), reinterpret_cast<const WAVEFORMATEX*>(wave),
                 static_cast<UINT32>(format.size())),
             "MFInitMediaTypeFromWaveFormatEx");
    if (adts) {
      const uint8_t kAdtsUserData[] = {0x01, 0x00, 0xFE, 0x00, 0x00, 0x00,
                                       0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
      CHECK_HR(type->SetUINT32(MF_MT_AAC_PAYLOAD_TYPE, 1), "payload type");
      CHECK_HR(type->SetBlob(MF_MT_USER_DATA, kAdtsUserData,
                             sizeof(kAdtsUserData)),
               "user data");
    }
    CHECK_HR(transform_->SetInputType(0, type.Get(), 0), "SetInputType");
    return ConfigureOutput();
  }

  // As MediaFoundationAudioDecoder::ConfigureOutput(): the first float type.
  bool ConfigureOutput() {
    output_sample_.Reset();
    for (DWORD index = 0;; ++index) {
      ComPtr<IMFMediaType> type;
      HRESULT hr = transform_->GetOutputAvailableType(0, index, &type);
      if (FAILED(hr)) {
        Fail("no float output type", hr);
        return false;
      }
      GUID subtype = GUID_NULL;
      type->GetGUID(MF_MT_SUBTYPE, &subtype);
      if (subtype != MFAudioFormat_Float) {
        continue;
      }
      CHECK_HR(transform_->SetOutputType(0, type.Get(), 0), "SetOutputType");
      MFT_OUTPUT_STREAM_INFO info = {};
      CHECK_HR(transform_->GetOutputStreamInfo(0, &info), "GetOutputStreamInfo");
      UINT32 channels = 0, rate = 0, mask = 0;
      type->GetUINT32(MF_MT_AUDIO_NUM_CHANNELS, &channels);
      type->GetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, &rate);
      HRESULT mask_hr = type->GetUINT32(MF_MT_AUDIO_CHANNEL_MASK, &mask);
      channels_ = static_cast<int>(channels);
      rate_ = static_cast<int>(rate);
      printf("  output: float, %d channels, %d Hz, channel mask %s0x%X, "
             "stream flags 0x%lX, cbSize %lu, cbAlignment %lu\n",
             channels_, rate_, SUCCEEDED(mask_hr) ? "" : "(absent) ", mask,
             info.dwFlags, info.cbSize, info.cbAlignment);
      if (info.cbSize == 0 || channels_ <= 0) {
        Fail("unusable output stream info");
        return false;
      }
      output_sample_ = CreateSample(info.cbSize, static_cast<int>(info.cbAlignment));
      if (!output_sample_) {
        Fail("could not create the output sample");
        return false;
      }
      HRESULT begin =
          transform_->ProcessMessage(MFT_MESSAGE_NOTIFY_BEGIN_STREAMING, 0);
      CHECK_HR(begin, "NOTIFY_BEGIN_STREAMING");
      return true;
    }
  }

  bool Decode(const uint8_t* data, size_t size, LONGLONG time) {
    ComPtr<IMFSample> sample = CreateSample(static_cast<uint32_t>(size), 0);
    if (!sample || !FillSample(sample.Get(), data, size)) {
      Fail("could not create an input sample");
      return false;
    }
    CHECK_HR(sample->SetSampleTime(time), "SetSampleTime");
    CHECK_HR(transform_->ProcessInput(0, sample.Get(), 0), "ProcessInput");
    return Pump();
  }

  bool Drain() {
    CHECK_HR(transform_->ProcessMessage(MFT_MESSAGE_COMMAND_DRAIN, 0), "DRAIN");
    return Pump();
  }

  bool Pump() {
    bool changed = false;
    for (;;) {
      MFT_OUTPUT_DATA_BUFFER output = {};
      output.pSample = output_sample_.Get();
      DWORD status = 0;
      HRESULT hr = transform_->ProcessOutput(0, 1, &output, &status);
      if (output.pEvents) {
        output.pEvents->Release();
      }
      if (hr == MF_E_TRANSFORM_NEED_MORE_INPUT) {
        return true;
      }
      if (hr == MF_E_TRANSFORM_STREAM_CHANGE && !changed) {
        changed = true;
        ++stream_changes_;
        if (!ConfigureOutput()) {
          return false;
        }
        continue;
      }
      CHECK_HR(hr, "ProcessOutput");
      ComPtr<IMFMediaBuffer> buffer;
      CHECK_HR(output_sample_->ConvertToContiguousBuffer(&buffer),
               "ConvertToContiguousBuffer");
      uint8_t* data = nullptr;
      DWORD length = 0;
      CHECK_HR(buffer->Lock(&data, nullptr, &length), "Lock output");
      const size_t count = length / sizeof(float);
      const float* samples = reinterpret_cast<const float*>(data);
      for (size_t i = 0; i < count; ++i) {
        sum_squares_ += static_cast<double>(samples[i]) * samples[i];
        peak_ = std::max(peak_, std::fabs(samples[i]));
      }
      samples_ += count;
      frames_ += count / channels_;
      ++buffers_;
      buffer->SetCurrentLength(0);
      buffer->Unlock();
    }
  }

  int channels_ = 0, rate_ = 0, stream_changes_ = 0;
  size_t samples_ = 0, frames_ = 0, buffers_ = 0;
  double sum_squares_ = 0;
  float peak_ = 0;

 private:
  ComPtr<IMFTransform> transform_;
  ComPtr<IMFSample> output_sample_;
};

int RunAac(int argc, char** argv) {
  if (argc < 4) {
    return 2;
  }
  const std::vector<uint8_t> stream = ReadFile(argv[2]);
  const bool adts = strcmp(argv[3], "adts") == 0;
  static const int kRates[] = {96000, 88200, 64000, 48000, 44100, 32000, 24000,
                               22050, 16000, 12000, 11025, 8000,  7350};
  std::vector<AdtsFrame> frames;
  int object_type = 0, frequency_index = 0, channels = 0;
  for (size_t at = 0; at + 7 < stream.size();) {
    if (stream[at] != 0xFF || (stream[at + 1] & 0xF6) != 0xF0) {
      Fail("not an ADTS frame where one was expected");
      return 1;
    }
    const size_t header = (stream[at + 1] & 1) ? 7 : 9;
    const size_t size = (static_cast<size_t>(stream[at + 3] & 3) << 11) |
                        (static_cast<size_t>(stream[at + 4]) << 3) |
                        (stream[at + 5] >> 5);
    if (size <= header || at + size > stream.size()) {
      break;
    }
    if (frames.empty()) {
      object_type = (stream[at + 2] >> 6) + 1;
      frequency_index = (stream[at + 2] >> 2) & 0xF;
      channels = ((stream[at + 2] & 1) << 2) | (stream[at + 3] >> 6);
    }
    frames.push_back({at, header, size});
    at += size;
  }
  if (frames.empty() || frequency_index > 12) {
    Fail("no ADTS frames found");
    return 1;
  }
  const int rate = kRates[frequency_index];
  printf("AAC %s: %zu frames, object type %d, %d Hz, %d channels, handed "
         "over %s\n",
         argv[2], frames.size(), object_type, rate, channels,
         adts ? "with ADTS headers" : "as bare frames with AudioSpecificConfig");

  // The engine's audio decoder starts Media Foundation first
  // (InitializeMediaFoundation() in Chromium) and gives up if that fails.
  const HRESULT startup = MFStartup(MF_VERSION, MFSTARTUP_LITE);
  printf("  MFStartup(MFSTARTUP_LITE): 0x%08lX\n",
         static_cast<unsigned long>(startup));
  if (FAILED(startup)) {
    Fail("MFStartup failed: the engine would report AAC as not decodable here",
         startup);
  }

  AacProbe probe;
  if (!probe.Create(object_type, frequency_index, rate, channels, adts)) {
    return 1;
  }
  LONGLONG time = 0;
  for (size_t i = 0; i < frames.size(); ++i) {
    const AdtsFrame& frame = frames[i];
    const size_t skip = adts ? 0 : frame.header_size;
    if (!probe.Decode(stream.data() + frame.offset + skip, frame.size - skip,
                      time)) {
      printf("  failed at frame %zu\n", i);
      return 1;
    }
    time += 10000000LL * 1024 / rate;
  }
  if (!probe.Drain()) {
    return 1;
  }
  const double rms =
      probe.samples_ ? sqrt(probe.sum_squares_ / probe.samples_) : 0;
  printf("  decoded: %zu buffers, %zu sample frames (%.2f s at %d Hz, %d "
         "channels), RMS %.4f, peak %.4f, stream changes %d\n",
         probe.buffers_, probe.frames_,
         probe.rate_ ? static_cast<double>(probe.frames_) / probe.rate_ : 0.0,
         probe.rate_, probe.channels_, rms, probe.peak_, probe.stream_changes_);
  // Every ADTS frame holds 1024 sample frames; the decoder may hold back or
  // drop the first one.
  if (probe.frames_ + 2048 < frames.size() * 1024) {
    Fail("too few samples decoded");
  }
  if (rms < 0.01 || probe.peak_ > 1.5f) {
    Fail("the decoded sound is silent or out of range");
  }
  if (probe.rate_ != rate || probe.channels_ != channels) {
    Fail("output format differs from the stream's");
  }
  return g_failures ? 1 : 0;
}

}  // namespace

int main(int argc, char** argv) {
  setvbuf(stdout, nullptr, _IONBF, 0);
  int code = 2;
  if (argc >= 2 && strcmp(argv[1], "h264") == 0) {
    code = RunH264(argc, argv);
  } else if (argc >= 2 && strcmp(argv[1], "aac") == 0) {
    code = RunAac(argc, argv);
  }
  if (code == 2) {
    printf("usage: mft_probe h264 STREAM PTS WIDTH HEIGHT [low-delay] | "
           "mft_probe aac SOUND raw|adts\n");
  } else {
    printf(code == 0 ? "RESULT: ok\n" : "RESULT: FAILED\n");
  }
  return code;
}
