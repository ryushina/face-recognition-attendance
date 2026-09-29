# Local recognition pipeline

## Decision

Use OpenCV YuNet face detection and five-point landmarks followed by OpenCV
SFace alignment and feature extraction. One YuNet pass supplies the live face
boxes, landmarks, and input to SFace, so the desktop application does not run
the legacy YOLO/Haar detector in parallel with a second recognition detector.
Run the model on CPU through OpenCV DNN. Runtime does not download or update
models.

OpenCV documents this same pair through `FaceDetectorYN` and
`FaceRecognizerSF`: detection returns a face box and five landmarks,
`alignCrop` uses them to align the face, and `feature` extracts its numeric
representation. This keeps detection, alignment, and embedding extraction in
the existing OpenCV dependency instead of adding a second inference framework.

## Exact model artifacts

The setup script downloads each file from a pinned OpenCV Zoo Git commit and
verifies SHA-256 before saving it under `models/`:

| Purpose | Artifact and revision | SHA-256 | License stated by the model project |
| --- | --- | --- | --- |
| Detection and five landmarks | `face_detection_yunet_2023mar.onnx`, commit `f12e12798e8314f7c074a6656816c048dcc95b7a` | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` | MIT, per YuNet model directory |
| Alignment and recognition | `face_recognition_sface_2021dec.onnx`, commit `ba91a3b91d00d76e86540d4013f944bd6b514e39` | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` | Apache-2.0, per SFace model directory |

The exact SFace weight's training data and license scope have an unresolved
question in [OpenCV Zoo issue 313](https://github.com/opencv/opencv_zoo/issues/313)
as of 2026-09-29. The model-directory README states Apache-2.0. Keep the
artifact local for development; resolve model rights and training-data
provenance before distributing it or using it for a school deployment.

The model files are ignored by Git and can be recreated with:

```powershell
.\.venv\Scripts\python.exe scripts\download_models.py
```

The pins are from the immutable source revisions recorded above. If upstream
changes models, it will not change the artifacts this project requests.

## Preprocessing and outputs

Frames and image files enter OpenCV as BGR pixels. YuNet receives the full
source-resolution frame and returns `[x, y, width, height]` and five landmark
pairs. For one detected face, SFace `alignCrop(frame, detection)` makes its
standard aligned face; SFace `feature(aligned)` produces a 128-value vector.
The application converts that vector to finite `float32` values and L2
normalizes it. Enrollment and live recognition must use this same path.

Model and preprocessing IDs are stored with saved sample embeddings. The
current IDs are `yunet:face_detection_yunet_2023mar:<sha256>` and
`sface:face_recognition_sface_2021dec:<sha256>` with preprocessing ID
`opencv-face-recognizer-sf-aligncrop-bgr-float32-l2-v1`.

YuNet uses the fixed-input 2023 model for compatibility with the pinned
OpenCV 4.12 runtime. Its expected input size is 320 by 320; OpenCV's
`FaceDetectorYN.setInputSize` handles the camera/image dimensions as in the
official example. Recheck this on the eventual target platform.

## Failure and limits

Missing or invalid model files stop recognition with a path-specific error.
No-face, multiple-face, invalid or non-finite feature results cannot identify a
student. An embedding is not a probability. Similarity thresholds, false
accept/reject rates, anti-spoofing, and Raspberry Pi performance are not
established by this model selection. The official OpenCV sample similarity
threshold is not adopted as a school threshold; T28 owns calibration.

## References

- [OpenCV DNN face detection and recognition tutorial](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html)
- [OpenCV Zoo YuNet README and MIT license](https://github.com/opencv/opencv_zoo/tree/f12e12798e8314f7c074a6656816c048dcc95b7a/models/face_detection_yunet)
- [OpenCV Zoo SFace README and Apache-2.0 license](https://github.com/opencv/opencv_zoo/tree/ba91a3b91d00d76e86540d4013f944bd6b514e39/models/face_recognition_sface)
- [OpenCV Zoo SFace model rights and training-data question](https://github.com/opencv/opencv_zoo/issues/313)
