# TASKS-007: Image and Video Submissions

**User Story:** D5 (Submit text, images, or video), D6 evidence for images and video
**User Flow:** Flow 5 - Submitting work and getting feedback (SPEC §6.6, §12 steps 6-7)
**Priority:** P0 (MVP)

---

## Prerequisites

- [x] `mediaEnabled` flag from TASKS_001 gates all upload UI
- [x] Storage: `data/submissions/<session>/` and `data/frames/`
- [x] Python or Node wrappers for ffmpeg, ffprobe and faster-whisper

---

## STEP 1: Image Submissions (build first)

- [x] Drag-and-drop and file picker in the submission area (`design/Practice.dc.html`)
- [x] Validate type and size; save `SubmissionAsset(kind=image)`
- [x] Thumbnail preview with remove
- [x] Send images to the model as `image_url` parts with the checklist; warn if the configured model is not vision-capable
- [x] Feedback evidence refers to image regions; show the region next to the comment

## STEP 2: Video Intake

- [x] Accept clip upload
- [x] Read duration with ffprobe; reject over ~3 minutes with "split it" message
- [x] Save `SubmissionAsset(kind=video, duration_s)`

## STEP 3: Process Locally

**Question to ask:** "How do we give the model enough of a clip without sending the video?"

- [x] Keyframes: scene-change detection plus a frame every 2 s
- [x] Cap frames per clip; sample evenly if over the cap
- [x] Save `VideoFrame(timestamp_s, file_path)`
- [x] Transcribe audio with timestamps (faster-whisper)
- [x] Collect metadata: duration, cut count, cut timestamps, shot lengths
- [x] Store in `processed_json`
- [x] Progress UI for frames, transcript, cuts
- [x] Run as background job; do not block the UI

## STEP 4: Send and Show Feedback

- [x] Send frames with timestamps + transcript + cut data + checklist to the feedback prompt
- [x] Evidence by frame number or timestamp (e.g. "0:12-0:18")
- [x] Session view shows the referenced frame beside the comment
- [x] Mixed submissions (text + images + video) handled together

---

## Error Scenarios

- [x] ffmpeg failure: show reason, keep the upload for retry
- [x] No audio track: skip transcript, continue
- [x] Whisper missing: process frames and cuts only, note it
- [x] Unsupported format: clear message

## Edge Cases

- [x] Very short clip with few frames
- [x] Clip exactly at the limit
- [x] Large image files: downscale before sending

## Testing

- [x] Test duration limit rejection
- [x] Test frame cap and even sampling
- [x] Test feedback evidence resolves to a stored frame
- [x] Acceptance: image feedback names specific parts; video feedback cites timestamps with frames shown
- [x] Acceptance: works with network off except the LLM server

---

## Task Summary

| Category | Tasks | Status |
| --- | --- | --- |
| Prerequisites | 3 | Done |
| Step 1-4 | 20 | Done |
| Errors | 4 | Done |
| Edge Cases | 3 | Done |
| Testing | 5 | Done |
| **Total** | **35** | **35/35 done** |

---

**Task List Version:** 1.1
**Created:** 2026-11-03
