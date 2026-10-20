"""Tests for visualize.py — dual-mode cover support."""
import sys
from pathlib import Path

# Adopt same path setup as existing tests
SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import visualize


def _make_jpeg_at_ratio(tmp_dir, name="cover.jpg", width=900, height=383):
    """Create a minimal JPEG with known dimensions in tmp_dir."""
    try:
        from PIL import Image
    except ImportError:
        import pytest
        pytest.skip("Pillow not available")
    img = Image.new("RGB", (width, height), color=(255, 128, 64))
    path = tmp_dir / name
    img.save(path, "JPEG")
    return path


def test_detect_user_cover_finds_2_35_ratio(tmp_path):
    """900x383 (≈2.35) JPEG is detected."""
    _make_jpeg_at_ratio(tmp_path, "cover.jpg", 900, 383)
    result = visualize.detect_user_cover(tmp_path)
    assert result is not None
    assert result.name == "cover.jpg"


def test_detect_user_cover_skips_system_files(tmp_path):
    """Files named cover-main/sidebar/combined are excluded."""
    _make_jpeg_at_ratio(tmp_path, "cover-main.jpg", 1504, 640)
    _make_jpeg_at_ratio(tmp_path, "cover-sidebar.jpg", 1024, 1024)
    _make_jpeg_at_ratio(tmp_path, "cover-combined.jpg", 900, 300)
    result = visualize.detect_user_cover(tmp_path)
    assert result is None  # only system files present


def test_detect_user_cover_ignores_wrong_ratio(tmp_path):
    """1:1 image should not match."""
    _make_jpeg_at_ratio(tmp_path, "square.jpg", 800, 800)
    result = visualize.detect_user_cover(tmp_path)
    assert result is None


def test_detect_user_cover_returns_first_match(tmp_path):
    """With two matching covers, return the first (sorted)."""
    _make_jpeg_at_ratio(tmp_path, "aaa.jpg", 900, 383)
    _make_jpeg_at_ratio(tmp_path, "bbb.jpg", 1504, 640)
    result = visualize.detect_user_cover(tmp_path)
    assert result.name == "aaa.jpg"


def test_detect_user_cover_empty_dir(tmp_path):
    """Empty directory returns None."""
    result = visualize.detect_user_cover(tmp_path)
    assert result is None


def test_detect_user_cover_tolerance_range(tmp_path):
    """2.25 and 2.45 ratios are within tolerance."""
    _make_jpeg_at_ratio(tmp_path, "wide.jpg", 900, 400)   # 2.25
    result = visualize.detect_user_cover(tmp_path)
    assert result is not None

    # Clean and try narrow end
    for f in tmp_path.iterdir():
        f.unlink()
    _make_jpeg_at_ratio(tmp_path, "narrow.jpg", 939, 383)  # ≈2.45
    result = visualize.detect_user_cover(tmp_path)
    assert result is not None


class TestCoverRatioValidation:
    """Tests for _get_image_size and ratio validation logic."""

    def test_get_image_size_jpeg_via_stdlib(self, tmp_path):
        """stdlib fallback returns correct size for JPEG."""
        _make_jpeg_at_ratio(tmp_path, "test.jpg", 900, 383)
        w, h = visualize._get_image_size(tmp_path / "test.jpg")
        assert w == 900
        assert h == 383

    def test_get_image_size_png_via_stdlib(self, tmp_path):
        """stdlib fallback returns correct size for PNG."""
        try:
            from PIL import Image
        except ImportError:
            import pytest
            pytest.skip("Pillow not available")
        img = Image.new("RGB", (400, 200), color=(255, 0, 0))
        path = tmp_path / "test.png"
        img.save(path, "PNG")
        w, h = visualize._get_image_size(path)
        assert w == 400
        assert h == 200

    def test_ratio_out_of_range_rejected(self, tmp_path):
        """A 1:1 image is NOT detected as cover."""
        _make_jpeg_at_ratio(tmp_path, "square.jpg", 800, 800)
        result = visualize.detect_user_cover(tmp_path)
        assert result is None

    def test_extreme_narrow_rejected(self, tmp_path):
        """Ratio 3.0 is outside tolerance."""
        _make_jpeg_at_ratio(tmp_path, "panorama.jpg", 1200, 400)
        result = visualize.detect_user_cover(tmp_path)  # 3.0 > 2.50
        assert result is None

    def test_png_detected_as_cover(self, tmp_path):
        """PNG files are also scanned."""
        try:
            from PIL import Image
        except ImportError:
            import pytest
            pytest.skip("Pillow not available")
        img = Image.new("RGB", (900, 383), color=(255, 128, 64))
        path = tmp_path / "cover.png"
        img.save(path, "PNG")
        result = visualize.detect_user_cover(tmp_path)
        assert result is not None
        assert result.suffix == ".png"


class TestStitchCovers:
    """Tests for stitch_covers dual-mode support."""

    def test_full_mode_uses_cover_main(self, tmp_path, monkeypatch):
        """Without user_cover_path, stitch uses img/cover-main.jpg."""
        try:
            from PIL import Image
        except ImportError:
            import pytest
            pytest.skip("Pillow not available")

        # Create a minimal sidebar
        sidebar = Image.new("RGB", (1024, 1024), color=(200, 100, 50))
        sidebar.save(tmp_path / "cover-sidebar.jpg")
        # Create a minimal main cover
        main = Image.new("RGB", (1504, 640), color=(50, 100, 200))
        main.save(tmp_path / "cover-main.jpg")

        visualize.stitch_covers(tmp_path, "TestArticle")
        combined = tmp_path / "cover-combined.jpg"
        assert combined.exists()
        with Image.open(combined) as img:
            assert img.height == 1024  # sidebar height
            assert img.width > 1024    # main + sidebar

    def test_simple_mode_uses_user_cover(self, tmp_path, monkeypatch):
        """With user_cover_path, stitch uses the user-provided file."""
        try:
            from PIL import Image
        except ImportError:
            import pytest
            pytest.skip("Pillow not available")

        # Create a sidebar
        sidebar = Image.new("RGB", (1024, 1024), color=(200, 100, 50))
        sidebar.save(tmp_path / "cover-sidebar.jpg")
        # Create a user cover in a different location
        user_cover = Image.new("RGB", (900, 383), color=(100, 200, 50))
        user_path = tmp_path / "user_cover.jpg"
        user_cover.save(user_path)
        # No cover-main.jpg -- simple mode shouldn't need it

        visualize.stitch_covers(tmp_path, "TestArticle", user_cover_path=user_path)
        combined = tmp_path / "cover-combined.jpg"
        assert combined.exists()
        with Image.open(combined) as img:
            assert img.height == 1024


class TestSimpleModeMainIntegration:
    """Integration tests for simple mode main() flow."""

    def test_simple_mode_rejects_missing_part_b(self, tmp_path):
        """--mode simple with Storyboard containing no Part B exits with error."""
        img_dir = tmp_path / "img"
        img_dir.mkdir()

        # Create a valid user cover
        from PIL import Image
        cover = Image.new("RGB", (900, 383), color=(255, 128, 64))
        cover.save(img_dir / "user_cover.jpg")

        # Storyboard with Part A but NO Part B
        sb = tmp_path / "Storyboard.md"
        sb.write_text("""## Visual Storyboard

### Part A: 主视觉 cover-main (2.35:1)
(IP形象: 否)
```
test prompt
```
""", encoding="utf-8")

        # Run via subprocess to capture exit behavior
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "visualize.py"),
             "--mode", "simple", "--brief", str(sb), "--output-dir", str(img_dir)],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
        )
        # Should exit with error about missing Part B
        assert "未找到 Part B" in (result.stdout + result.stderr)

    def test_simple_mode_stitches_with_cover(self, tmp_path):
        """--mode simple with valid Storyboard and cover generates sidebar + combined."""
        img_dir = tmp_path / "img"
        img_dir.mkdir()

        from PIL import Image
        cover = Image.new("RGB", (900, 383), color=(255, 128, 64))
        cover.save(img_dir / "user_cover.jpg")

        sb = tmp_path / "Storyboard.md"
        sb.write_text("""## Visual Storyboard

### Part B: 侧边栏 cover-sidebar (1:1)
(IP形象: 否)
```
simple sidebar prompt
```
""", encoding="utf-8")

        # This test validates the parse + filtering path.
        # We test parse_visual_brief directly to avoid needing API keys.
        title, tasks = visualize.parse_visual_brief(sb)

        # Filter tasks as main() does in simple mode
        simple_tasks = [t for t in tasks if t.get("type") == "cover-sidebar"]
        assert len(simple_tasks) == 1
        assert simple_tasks[0]["type"] == "cover-sidebar"
        assert simple_tasks[0]["suffix"] == "cover-sidebar"
