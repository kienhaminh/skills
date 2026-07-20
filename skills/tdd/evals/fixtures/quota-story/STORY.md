# Upload quota

An upload is accepted when `used + size <= limit` and rejected above the limit. Inputs are
non-negative integers. Whether a rejected upload sends a notification is not specified.
