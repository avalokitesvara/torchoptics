"""This module defines functions to generate airy and sinc profiles."""

from typing import Optional

import torch
from torch import Tensor
from torch.special import bessel_j1  # Bessel function of the first kind

from ..functional import initialize_tensor
from ..planar_geometry import PlanarGeometry
from ..type_defs import Vector2

__all__ = ["airy", "sinc"]


def airy(
    shape: Vector2, scale: float, spacing: Optional[Vector2] = None, offset: Optional[Vector2] = None
) -> Tensor:
    r"""
    Generates an Airy pattern profile.

    The Airy pattern is defined by the following equation:

    .. math::
        \psi(r) = \left( \frac{2 J_1(\frac{r}{a})}{\frac{r}{a}} \right)^2

    where:

    - :math:`r` is the radial distance from the center of the diffraction pattern.
    - :math:`J_1` is the Bessel function of the first kind.
    - :math:`a` is the scaling factor that determines the size of the Airy disk.

    Args:
        shape (Vector2): Number of grid points along the planar dimensions.
        scale (float): A scaling factor that determines the size of the Airy disk.
        spacing (Optional[Vector2]): Distance between grid points along planar dimensions. Default: if
            `None`, uses a global default.
        offset (Optional[Vector2]): Center coordinates of the profile. Default: `(0, 0)`.

    Returns:
        Tensor: The generated Airy profile.
    """
    x, y = PlanarGeometry(shape, 0, spacing, offset).meshgrid()
    r = torch.sqrt(x**2 + y**2)
    scaled_r = r / scale
    airy_pattern = (2 * bessel_j1(scaled_r) / (scaled_r)) ** 2  # pylint: disable=not-callable
    airy_pattern[r == 0] = 1.0  # Handle the value at r = 0
    return airy_pattern


def sinc(
    shape: Vector2, scale: Vector2, spacing: Optional[Vector2] = None, offset: Optional[Vector2] = None
) -> Tensor:
    r"""
    Generates a sinc profile.

    The sinc profile is defined by the following equation:

    .. math::
        \psi(x, y) = \text{sinc}\left(\frac{x}{a}\right) \cdot \text{sinc}\left(\frac{y}{b}\right)

    where:

    - :math:`\text{sinc}(x) = \frac{\sin(\pi x)}{\pi x}` is the normalized sinc function.
    - :math:`a` and :math:`b` are the scaling factors along the x and y dimensions, respectively.

    Args:
        shape (Vector2): Number of grid points along the planar dimensions.
        scale (Vector2): The two scaling factors (widths) of the sinc function in the x and y directions.
        spacing (Optional[Vector2]): Distance between grid points along planar dimensions. Default: if
            `None`, uses a global default.
        offset (Optional[Vector2]): Center coordinates of the profile. Default: `(0, 0)`.

    Returns:
        Tensor: The generated sinc profile.
    """
    x, y = PlanarGeometry(shape, 0, spacing, offset).meshgrid()
    scale = initialize_tensor("scale", scale, (2,), fill_value=True, validate_positive=True)
    sinc_pattern = torch.sinc(x / scale[0]) * torch.sinc(y / scale[1])
    return sinc_pattern