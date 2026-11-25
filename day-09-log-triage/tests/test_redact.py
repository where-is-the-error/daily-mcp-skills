"""마스킹 — 지운 뒤 남은 것 0."""

from __future__ import annotations

import pytest

from log_triage.redact import _luhn, mask_line, redact_text


def test_password_value_masked_key_kept():
    out = mask_line("login password=hunter2 ok")
    assert "hunter2" not in out
    assert out.startswith("login password=<redacted:password>")


def test_api_key_masked():
    out = mask_line("call api_key=abcd1234efgh5678 done")
    assert "abcd1234efgh5678" not in out


def test_email_masked():
    out = mask_line("user kim@example.com logged in")
    assert "kim@example.com" not in out
    assert "<redacted:email>" in out


def test_ip_masked():
    out = mask_line("client 10.0.4.18 closed")
    assert "10.0.4.18" not in out


def test_jwt_masked():
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.dQw4w9WgXcQ"
    out = mask_line(f"Authorization: {token}")
    assert token not in out


def test_bearer_masked():
    out = mask_line("Authorization: Bearer abcdefghijklmnop")
    assert "abcdefghijklmnop" not in out


def test_aws_key_masked():
    out = mask_line("using key AKIAIOSFODNN7EXAMPLE region")
    assert "AKIAIOSFODNN7EXAMPLE" not in out


def test_github_token_masked():
    out = mask_line("token ghp_abcdefghijklmnopqrstuvwxyz0123")
    assert "ghp_abcdefghijklmnop" not in out


def test_private_key_block_masked():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----"
    out = redact_text(text)
    assert "MIIEow" not in "\n".join(line for _, line in out.texts)


def test_card_needs_luhn():
    assert _luhn("4242 4242 4242 4242")
    assert not _luhn("2026 11 25 10 40 47")


def test_valid_card_masked():
    out = mask_line('payload {"card":"4242 4242 4242 4242"}')
    assert "4242 4242 4242 4242" not in out


def test_invalid_card_left_alone():
    out = mask_line("timestamp 2026-11-25T10:40:47")
    assert "2026-11-25T10:40:47" in out


def test_phone_masked():
    out = mask_line("call 010-3156-8044 now")
    assert "010-3156-8044" not in out


def test_url_token_masked():
    out = mask_line("GET /reset?token=abcdef123456&next=/home")
    assert "abcdef123456" not in out


def test_counts_by_kind():
    result = redact_text("a@b.co\n10.0.0.1\npassword=x\n")
    assert result.counts["email"] == 1
    assert result.counts["ip"] == 1
    assert result.counts["password"] == 1
    assert result.total == 3


def test_line_numbers_preserved():
    result = redact_text("first\nsecond a@b.co\nthird\n")
    assert [number for number, _ in result.texts] == [1, 2, 3]


def test_residual_zero_after_masking():
    text = ("password=hunter2\n"
            "Authorization: Bearer abcdefghijklmnop\n"
            "user kim@example.com from 10.0.0.1\n"
            "card 4242 4242 4242 4242\n"
            "phone 010-3156-8044\n"
            "key AKIAIOSFODNN7EXAMPLE\n")
    result = redact_text(text)
    assert result.residual_total == 0
    assert result.total >= 6


def test_normal_lines_untouched():
    line = "2026-11-25 09:00:01 INFO  [api] request done duration_ms=24"
    assert mask_line(line) == line


def test_length_roughly_preserved():
    result = redact_text("user kim@example.com\n")
    assert abs(result.chars_before - result.chars_after) < 20


def test_changed_lines_counted():
    result = redact_text("clean line\na@b.co\npassword=x\n")
    assert result.lines_changed == 2


def test_messy_example_no_residual():
    from conftest import MESSY
    text = MESSY.read_text(encoding="utf-8")
    result = redact_text(text)
    assert result.total >= 6
    assert result.residual_total == 0


def test_masked_output_keeps_log_shape():
    from conftest import MESSY
    text = MESSY.read_text(encoding="utf-8")
    result = redact_text(text)
    masked = "\n".join(line for _, line in result.texts)
    assert len(masked.splitlines()) == len(text.splitlines())
    assert "2026-11-25 10:00:02,200 INFO" in masked
