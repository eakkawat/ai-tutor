# TASKS-007: Image and Video Submissions

**User Story:** D5 (Submit text, images, or video), D6 evidence for images and video
**User Flow:** Flow 5 - Submitting work and getting feedback (SPEC §6.6, §12 steps 6-7)
**Priority:** P0 (MVP)

---

## Prerequisites

- [ ] `mediaEnabled` flag from TASKS_001 gates all upload UI
- [ ] Storage: `data/submissions/<session>/` and `data/frames/`
- [ ] Python or Node wrappers for ffmpeg, ffprobe and faster-whisper

---

## STEP 1: Image Submissions (build first)

- [ ] Drag-and-drop and file picker in the submission area (`design/Practice.dc.html`)
- [ ] Validate type and size; save `SubmissionAsset(kind=image)`
- [ ] Thumbnail preview with remove
- [ ] Send images to the model as `image_url` parts with the checklist; warn if the configured model is not vision-capable
- [ ] Feedback evidence refers to image regions; show the region next to the comment

## STEP 2: Video Intake

- [ ] Accept clip upload
- [ ] Read duration with ffprobe; reject over ~3 minutes with "split it" message
- [ ] Save `SubmissionAsset(kind=video, duration_s)`

## STEP 3: Process Locally

**Question to ask:** "How do we give the model enough of a clip without sending the video?"

- [ ] Keyframes: scene-change detection plus a frame every 2 s
- [ ] Cap frames per clip; sample evenly if over the cap
- [ ] Save `VideoFrame(timestamp_s, file_path)`
- [ ] Transcribe audio with timestamps (faster-whisper)
- [ ] Collect metadata: duration, cut count, cut timestamps, shot lengths
- [ ] Store in `processed_json`
- [ ] Progress UI for frames, transcript, cuts
- [ ] Run as background job; do not block the UI

## STEP 4: Send and Show Feedback

- [ ] Send frames with timestamps + transcript + cut data + checklist to the feedback prompt
- [ ] Evidence by frame number or timestamp (e.g. "0:12-0:18")
- [ ] Session view shows the referenced frame beside the comment
- [ ] Mixed submissions (text + images + video) handled together

---

## Error Scenarios

- [ ] ffmpeg failure: show reason, keep the upload for retry
- [ ] No audio track: skip transcript, continue
- [ ] Whisper missing: process frames and cuts only, note it
- [ ] Unsupported format: clear message

## Edge Cases

- [ ] Very short clip with few frames
- [ ] Clip exactly at the limit
- [ ] Large image files: downscale before sending

## Testing

- [ ] Test duration limit rejection
- [ ] Test frame cap and even sampling
- [ ] Test feedback evidence resolves to a stored frame
- [ ] Acceptance: image feedback names specific parts; video feedback cites timestamps with frames shown
- [ ] Acceptance: works with network off except the LLM server

---

## Task Summary

| Category      | Tasks  | Status          |
| ------------- | ------ | --------------- |
| Prerequisites | 3      | Pending         |
| Step 1-4      | 26     | Pending         |
| Errors        | 4      | Pending         |
| Edge Cases    | 3      | Pending         |
| Testing       | 5      | Pending         |
| **Total**     | **41** | **0% Complete** |

---

**Task List Version:** 1.0
**Created:** 2026-11-03
