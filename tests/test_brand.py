"""Brand assets ship with the integration and are served by Home Assistant."""

from __future__ import annotations

import pathlib
import struct

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.subzero.const import DOMAIN

BRAND_DIR = (
    pathlib.Path(__file__).parent.parent / "custom_components" / DOMAIN / "brand"
)

# Names the brands integration is willing to serve. Anything else in the
# directory is ignored, so only these are worth asserting on.
SERVED_IMAGES = ("icon.png", "icon@2x.png", "dark_icon.png", "dark_icon@2x.png")


def png_size(path: pathlib.Path) -> tuple[int, int]:
    """Read the pixel dimensions out of a PNG's IHDR chunk."""
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", header[16:24])


def test_brand_assets_are_present() -> None:
    """The icon files exist and are exported at the expected sizes."""
    expected = {
        "icon.png": (512, 512),
        "icon@2x.png": (1024, 1024),
        "dark_icon.png": (512, 512),
        "dark_icon@2x.png": (1024, 1024),
    }
    for name, size in expected.items():
        path = BRAND_DIR / name
        assert path.is_file(), f"missing brand asset {name}"
        assert png_size(path) == size


async def test_brand_images_are_served(hass: HomeAssistant, hass_client) -> None:
    """Home Assistant serves the files from the repo rather than the CDN."""
    assert await async_setup_component(hass, "brands", {})

    client = await hass_client()
    for name in SERVED_IMAGES:
        response = await client.get(f"/api/brands/integration/{DOMAIN}/{name}")
        assert response.status == 200
        body = await response.read()
        # Byte equality proves the image came from this repo: the CDN has no
        # entry for a custom domain and would return its placeholder instead.
        assert body == (BRAND_DIR / name).read_bytes(), f"{name} was not served locally"
