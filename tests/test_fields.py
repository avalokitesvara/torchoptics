import unittest

import matplotlib.pyplot as plt
import numpy as np
import torch
from scipy.special import fresnel

from torchoptics import CoherenceField, Field, PlanarGeometry, PolarizedField
from torchoptics.elements import Modulator
from torchoptics.functional import outer2d
from torchoptics.propagation import VALID_PROPAGATION_METHODS


class TestField(unittest.TestCase):

    def test_initialization(self):
        shape = (10, 11)
        data = torch.ones(shape, dtype=torch.cdouble)
        z = 5.0
        spacing = 1.0
        offset = None
        wavelength = 0.3
        pg = Field(data, wavelength, z, spacing, offset)

        self.assertTrue(torch.equal(pg.data, torch.ones(shape, dtype=torch.cdouble)))
        self.assertTrue(torch.equal(pg.z, torch.tensor(5.0, dtype=torch.double)))
        self.assertTrue(torch.equal(pg.spacing, torch.tensor([1.0, 1.0], dtype=torch.double)))
        self.assertTrue(torch.equal(pg.offset, torch.tensor([0.0, 0.0], dtype=torch.double)))
        self.assertTrue(torch.equal(pg.wavelength, torch.tensor(0.3, dtype=torch.double)))
        with self.assertRaises(TypeError):
            Field(torch.ones(10, 10), spacing=1, wavelength=1, propagation_method=None)
        with self.assertRaises(ValueError):
            Field(torch.ones(10, 10), spacing=1, wavelength=1, propagation_method="Incorrect")
        with self.assertRaises(TypeError):
            Field("Wrong type", spacing=1, wavelength=1, interpolation_mode=None)
        with self.assertRaises(ValueError):
            Field(torch.ones(10), spacing=1, wavelength=1)

    @staticmethod
    def gaussian_2d(x, y, sigma_x, sigma_y, mu_x, mu_y):
        """
        Compute the value of a 2D Gaussian function.

        Parameters:
        - x, y: coordinates where the function is evaluated.
        - sigma_x, sigma_y: standard deviations of the Gaussian function along the x and y axes.
        - mu_x, mu_y: means of the Gaussian function along the x and y axes.

        Returns:
        - The value of the 2D Gaussian function at (x, y).
        """
        coefficient = 1 / (2 * torch.pi * sigma_x * sigma_y)
        exponent = -((x - mu_x) ** 2 / (2 * sigma_x**2) + (y - mu_y) ** 2 / (2 * sigma_y**2))
        return coefficient * torch.exp(exponent)

    def test_centroid_and_std(self):
        shape = (1001, 1000)
        z = 0
        spacing = 0.1753
        offset = (1.63, -0.64)
        wavelength = 1.0

        planar_geometry = PlanarGeometry(shape, z, spacing, offset)
        x, y = planar_geometry.meshgrid()

        sigma_x, sigma_y = 2.6, 1.75
        mu_x, mu_y = -2.34, 3.23
        data = (self.gaussian_2d(x, y, sigma_x, sigma_y, mu_x, mu_y)) ** 0.5  # Field

        field = Field(data.cdouble(), wavelength, z, spacing, offset)
        centroid = field.centroid()
        std = field.std()
        self.assertTrue(torch.allclose(centroid, torch.tensor([mu_x, mu_y], dtype=torch.double), atol=1e-3))
        self.assertTrue(torch.allclose(std, torch.tensor([sigma_x, sigma_y], dtype=torch.double), atol=1e-3))

    @staticmethod
    def analytical_square_aperture_field(x, L, N_f, wavelength, propagation_distance):
        S_minus, C_minus = fresnel((2 * N_f) ** 0.5 * (1 - 2 * x / L))
        S_plus, C_plus = fresnel((2 * N_f) ** 0.5 * (1 + 2 * x / L))
        Integral = 1 / 2**0.5 * (C_minus + C_plus) + 1j / 2**0.5 * (S_minus + S_plus)
        xv, yv = np.meshgrid(Integral, Integral)
        field = np.exp(1j * 2 * np.pi / wavelength * propagation_distance) / 1j * xv * yv
        return field

    def test_propagation_square_aperture(self):
        shape = 201
        spacing = 5e-6
        wavelength = 800e-9
        propagation_distance = 0.05

        devices = ["cpu", "cuda"] if torch.cuda.is_available() else ["cpu"]
        for device in devices:
            for propagation_method in VALID_PROPAGATION_METHODS:
                square_field = torch.ones(shape, shape, device=device)
                input_field = Field(
                    square_field.cdouble(),
                    spacing=spacing,
                    wavelength=wavelength,
                    propagation_method=propagation_method,
                ).to(device)
                output_field = input_field.propagate((shape, shape), propagation_distance, spacing=spacing)
                x = np.linspace(-spacing * shape / 2, spacing * shape / 2, shape)
                L = (shape - 1) * spacing
                N_f = (L / 2) ** 2 / (wavelength * propagation_distance)
                analytical_field = self.analytical_square_aperture_field(
                    x, L, N_f, wavelength, propagation_distance
                )

                self.assertTrue(np.allclose(output_field.data.cpu(), analytical_field, atol=1e-1))

    def test_offset(self):
        shape = 200
        spacing = 5e-6
        wavelength = 800e-9
        propagation_distance = 0.05

        for propagation_method in VALID_PROPAGATION_METHODS:

            square_field = torch.ones(shape, shape, dtype=torch.cdouble)
            input_field = Field(
                square_field,
                spacing=spacing,
                wavelength=wavelength,
                propagation_method=propagation_method,
            )
            output_field = input_field.propagate((shape, shape), propagation_distance, spacing=spacing)

            offset = (100 * spacing, -30 * spacing)
            offset_input_field = Field(
                square_field,
                spacing=spacing,
                wavelength=wavelength,
                offset=offset,
                propagation_method=propagation_method,
            )
            offset_output_field = offset_input_field.propagate(
                (shape, shape), propagation_distance, spacing=spacing
            )

            self.assertTrue(
                torch.allclose(offset_output_field.data[100:, :-30], output_field.data[:-100, 30:])
            )

    def test_asm_propagation(self):
        shape = 201
        spacing = 5e-6
        wavelength = 800e-9
        propagation_distance = 0.05

        square_field = torch.ones(shape, shape, dtype=torch.cdouble)
        input_field = Field(
            square_field,
            spacing=spacing,
            wavelength=wavelength,
            propagation_method="ASM",
            asm_pad_factor=0,
        )

        # Should not fail
        input_field.propagate((shape, shape), propagation_distance, spacing=input_field.spacing, offset=None)

        with self.assertRaises(ValueError):  # Should fail: propagation outside bounds
            input_field.propagate(
                (shape, shape), propagation_distance, spacing=input_field.spacing, offset=(1e-8, 0)
            )

    def test_asm_pad_factor(self):
        with self.assertRaises(ValueError):
            Field(torch.ones(10, 10), spacing=1, wavelength=1, asm_pad_factor=(1, 2, 3))
        with self.assertRaises(ValueError):
            Field(torch.ones(10, 10), spacing=1, wavelength=1, asm_pad_factor=(1, -2))
        with self.assertRaises(ValueError):
            Field(torch.ones(10, 10), spacing=1, wavelength=1, asm_pad_factor=(1, 2.2))

        shape = (100, 200)
        spacing = 5e-6
        wavelength = 800e-9
        propagation_distance = 0.05
        asm_pad_factor = (3, 2)

        square_field1 = torch.ones(shape[0], shape[1], dtype=torch.cdouble)
        input_field1 = Field(
            square_field1,
            spacing=spacing,
            wavelength=wavelength,
            propagation_method="ASM",
            asm_pad_factor=asm_pad_factor,
        )

        square_field2 = torch.zeros(
            (1 + 2 * asm_pad_factor[0]) * shape[0],
            (1 + 2 * asm_pad_factor[1]) * shape[1],
            dtype=torch.cdouble,
        )

        square_field2[
            asm_pad_factor[0] * shape[0] : (asm_pad_factor[0] + 1) * shape[0],
            asm_pad_factor[1] * shape[1] : (asm_pad_factor[1] + 1) * shape[1],
        ] = 1

        input_field2 = Field(
            square_field2,
            spacing=spacing,
            wavelength=wavelength,
            propagation_method="ASM",
            asm_pad_factor=0,
        )

        output_field1 = input_field1.propagate((shape[0], shape[1]), propagation_distance, spacing=spacing)
        output_field2 = input_field2.propagate((shape[0], shape[1]), propagation_distance, spacing=spacing)

        self.assertTrue(torch.allclose(output_field1.data, output_field2.data))

    def test_interpolation_modes(self):
        shape = (100, 100)
        spacing = 1e-6
        wavelength = 500e-9
        data = torch.ones(shape, dtype=torch.cdouble)
        field = Field(data, wavelength, spacing=spacing)

        for mode in ["nearest", "bilinear", "bicubic"]:
            field.interpolation_mode = mode
            self.assertEqual(field.interpolation_mode, mode)

        with self.assertRaises(ValueError):
            field.interpolation_mode = "invalid_mode"
        with self.assertRaises(TypeError):
            field.interpolation_mode = None

    def test_repr(self):
        field = Field(torch.ones(10, 10), spacing=1, wavelength=1)
        repr_str = repr(field)
        self.assertTrue("propagation_method" in repr_str)
        self.assertTrue("asm_pad_factor" in repr_str)
        self.assertTrue("interpolation_mode" in repr_str)

    def test_propagate_methods(self):
        field = Field(torch.ones(10, 10), spacing=1, wavelength=1)
        field_propagate_to_z = field.propagate_to_z(1)
        field_propagate_to_plane = field.propagate_to_plane(PlanarGeometry(10, 1, 1))
        field_propagate = field.propagate(10, 1, 1)
        self.assertTrue(torch.allclose(field_propagate_to_z.data, field_propagate.data))
        self.assertTrue(torch.allclose(field_propagate_to_plane.data, field_propagate.data))

        with self.assertRaises(TypeError):
            field.propagate_to_plane("Not a PlanarGeometry object")

    def test_modulate(self):
        field = Field(torch.ones(10, 10), spacing=1, wavelength=1)
        modulated_field = field.modulate(10 * torch.ones(10, 10))
        self.assertTrue(torch.allclose(modulated_field.data, 10 * torch.ones(10, 10, dtype=torch.cdouble)))

    def test_normalization(self):
        field = Field(torch.rand(10, 10), spacing=10e-6, wavelength=800e-9)
        normalized_field = field.normalize(2)
        self.assertTrue(torch.allclose(normalized_field.power(), torch.tensor(2, dtype=torch.double)))

    def test_inner(self):
        field = Field(torch.ones(10, 10), spacing=1, wavelength=1)
        inner = field.inner(field)
        self.assertTrue(torch.allclose(inner, torch.tensor(100, dtype=torch.cdouble)))
        with self.assertRaises(ValueError):
            field.inner(Field(torch.ones(5, 5), spacing=1, wavelength=1))

    def test_outer(self):
        field = Field(torch.ones(10, 10), spacing=1, wavelength=1)
        outer = field.outer(field)
        self.assertTrue(torch.allclose(outer, torch.ones(10, 10, 10, 10, dtype=torch.cdouble)))
        with self.assertRaises(ValueError):
            field.outer(Field(torch.ones(5, 5), spacing=1, wavelength=1))

    def test_visualize(self):
        shape = (10, 10)
        data = torch.ones(shape, dtype=torch.cdouble)
        field = Field(data, wavelength=1, spacing=1)

        # Test visualization of the field data
        fig = field.visualize(intensity=True, show=False, return_fig=True)
        self.assertIsInstance(fig, plt.Figure)


class TestPolarizedField(unittest.TestCase):

    def test_initialization(self):
        shape = (10, 10)
        data = torch.ones(3, *shape, dtype=torch.cdouble)
        z = 5.0
        spacing = 1.0
        offset = None
        wavelength = 0.3
        pg = PolarizedField(data, wavelength, z, spacing, offset)

        self.assertTrue(torch.equal(pg.data, torch.ones(3, *shape, dtype=torch.cdouble)))
        self.assertTrue(torch.equal(pg.z, torch.tensor(5.0, dtype=torch.double)))
        self.assertTrue(torch.equal(pg.spacing, torch.tensor([1.0, 1.0], dtype=torch.double)))
        self.assertTrue(torch.equal(pg.offset, torch.tensor([0.0, 0.0], dtype=torch.double)))
        self.assertTrue(torch.equal(pg.wavelength, torch.tensor(0.3, dtype=torch.double)))

        with self.assertRaises(ValueError):
            PolarizedField(torch.ones(2, 10, 10), spacing=1, wavelength=1)

    def test_normalization(self):
        field = PolarizedField(torch.rand(3, 10, 10), spacing=10e-6, wavelength=800e-9)
        normalized_field = field.normalize(2)
        self.assertTrue(torch.allclose(normalized_field.power(), torch.tensor(2, dtype=torch.double)))

    def test_modulate(self):
        field = PolarizedField(torch.ones(3, 10, 10), spacing=1, wavelength=1)
        modulated_field = field.modulate(10 * torch.ones(10, 10))
        self.assertTrue(torch.allclose(modulated_field.data, 10 * torch.ones(3, 10, 10, dtype=torch.cdouble)))


class TestSpatialCoherence(unittest.TestCase):

    def setUp(self):
        self.shape = (20, 21)
        self.wavelength = 795e-9
        self.z = 0
        self.spacing = 9.2e-6
        self.offset = (-102e-6, 83e-6)
        self.input_field = torch.rand(self.shape, dtype=torch.double) * torch.exp(
            2j * torch.pi * torch.rand(self.shape, dtype=torch.double)
        )
        self.input_spatial_coherence = outer2d(self.input_field, self.input_field)
        self.field = Field(self.input_field, self.wavelength, self.z, self.spacing, self.offset)
        self.spatial_coherence = CoherenceField(
            self.input_spatial_coherence, self.wavelength, self.z, self.spacing, self.offset
        )

    def test_intensity_equal_field_coherent(self):
        self.assertTrue(torch.allclose(self.field.intensity(), self.spatial_coherence.intensity()))

    def test_modulation_intensity(self):
        modulator = Modulator(
            torch.rand(self.shape) * torch.exp(2j * torch.pi * torch.rand(self.shape)),
            self.z,
            self.spacing,
            self.offset,
        )
        modulated_field = modulator.forward(self.field)
        modulated_spatial_coherence = modulator.forward(self.spatial_coherence)
        self.assertTrue(torch.allclose(modulated_field.intensity(), modulated_spatial_coherence.intensity()))

    def test_propagation_intensity(self):
        prop_shape = (23, 24)
        prop_z = 0.1
        prop_spacing = 9.0e-6
        prop_offset = (-11e-6, 50e-6)

        prop_field = self.field.propagate(prop_shape, prop_z, prop_spacing, prop_offset)
        prop_spatial_coherence = self.spatial_coherence.propagate(
            prop_shape, prop_z, prop_spacing, prop_offset
        )
        self.assertTrue(torch.allclose(prop_field.intensity(), prop_spatial_coherence.intensity()))

    def test_normalization_coherent(self):
        normalized_power = 2.53
        field = self.field.normalize(normalized_power)
        spatial_coherence = self.spatial_coherence.normalize(normalized_power)
        self.assertTrue(torch.allclose(field.intensity(), spatial_coherence.intensity()))
        self.assertTrue(
            torch.allclose(spatial_coherence.power(), torch.tensor(normalized_power, dtype=torch.double))
        )