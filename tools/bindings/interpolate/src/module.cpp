#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <iostream>
#include <future>
#include <sstream>

#include "interpolate.h"


namespace py = pybind11;

PYBIND11_MODULE(interpolate, m) {
    m.doc() = "Fast linear interpolator";

    m.def("interpolate", [](
        std::vector<py::array_t<double, py::array::c_style>> points,
        py::array_t<double, py::array::c_style> values,
        py::array_t<double, py::array::c_style> interp_points,
        size_t max_threads
    ) {
        size_t num_dims = points.size();

        if (values.ndim() == 0 || interp_points.ndim() == 0) {
            throw py::type_error("Only arrays are supported, not scalar values!");
        }

        for (auto arr : points) {
            if (arr.ndim() != 1) {
                throw py::type_error("'points' must be a list of 1D arrays!");
            }
        }

        if (num_dims != values.ndim()) {
            std::stringstream ss;
            ss << "Dimension mismatch! Grid is " << num_dims
               << "D but values are " << values.ndim() << "D!";
            throw py::type_error(ss.str());
        }

        if (interp_points.ndim() != 2) {
            throw py::type_error("'interp_points' should have shape (N, ndim).");
        }

        size_t interp_dims = interp_points.shape()[1];
        if (num_dims != interp_dims) {
            std::stringstream ss;
            ss << "Dimension mismatch! Grid is " << num_dims
               << "D but interpolation points are " << interp_dims << "D!";
            throw py::type_error(ss.str());
        }
        size_t num_elements = interp_points.shape()[0];
        double * out = new double[num_elements];

        auto values_info = values.request();
        auto interp_points_info = interp_points.request();


        // Reasonable thread defaults based on profiling. It seems that spawning
        // threads in powers of 2 yields optimal performance.
        size_t desired_threads;
        if (num_elements < 10000) {
            desired_threads = 1;
        } else if (num_elements < 4000000) {
            desired_threads = 2;
        } else if (num_elements < 160000000){
            desired_threads = 4;
        } else {
            desired_threads = 8;
        }
        size_t num_threads = std::min(desired_threads, max_threads);
        if (num_threads == 0) {
            num_threads = 1;
        }
        size_t stride = num_elements / num_threads;

        double * values_ptr = (double *) values_info.ptr,
               * interp_points_ptr = (double *) interp_points_info.ptr;

        if (num_dims == 1) {
            auto xs_info = points[0].request();

            double * xs_ptr = (double *) xs_info.ptr;

            if (num_threads == 1) {
                // For small arrays just compute in one thread
                interpolate_1d(
                    xs_ptr,
                    points[0].size(),
                    values_ptr,
                    interp_points_ptr,
                    out,
                    num_elements
                );
            } else {
                std::vector<std::future<void>> tasks;

                for (size_t i = 0; i < num_threads; i++) {
                    size_t index = i * stride;
                    tasks.push_back(
                        std::async(
                            &interpolate_1d,
                            xs_ptr,
                            xs_info.shape[0],
                            values_ptr,
                            &interp_points_ptr[index],
                            &out[index],
                            index + stride < num_elements ? stride : num_elements - index
                        )
                    );
                }
                for (auto &future : tasks) {
                    std::move(future);
                }
            }
        } else if (num_dims == 2) {
            auto xs_info = points[0].request();
            auto ys_info = points[1].request();

            double * xs_ptr = (double *) xs_info.ptr,
                   * ys_ptr = (double *) ys_info.ptr;

            if (num_threads == 1) {
                interpolate_2d(
                    xs_ptr,
                    points[0].size(),
                    ys_ptr,
                    points[1].size(),
                    values_ptr,
                    interp_points_ptr,
                    out,
                    num_elements
                );
            } else {
                std::vector<std::future<void>> tasks;

                for (size_t i = 0; i < num_threads; i++) {
                    size_t index = i * stride;
                    tasks.push_back(
                        std::async(
                            &interpolate_2d,
                            xs_ptr,
                            points[0].size(),
                            ys_ptr,
                            points[1].size(),
                            values_ptr,
                            &interp_points_ptr[index * num_dims],
                            &out[index],
                            index + stride < num_elements ? stride : num_elements - index
                        )
                    );
                }
                for (auto &future : tasks) {
                    std::move(future);
                }
            }
        } else if (num_dims == 3) {
            auto xs_info = points[0].request();
            auto ys_info = points[1].request();
            auto zs_info = points[2].request();

            double * xs_ptr = (double *) xs_info.ptr,
                   * ys_ptr = (double *) ys_info.ptr,
                   * zs_ptr = (double *) zs_info.ptr;

            if (num_threads == 1) {
                interpolate_3d(
                    xs_ptr,
                    points[0].size(),
                    ys_ptr,
                    points[1].size(),
                    zs_ptr,
                    points[2].size(),
                    values_ptr,
                    interp_points_ptr,
                    out,
                    num_elements
                );
            } else {
                std::vector<std::future<void>> tasks;

                for (size_t i = 0; i < num_threads; i++) {
                    size_t index = i * stride;
                    tasks.push_back(
                        std::async(
                            &interpolate_3d,
                            xs_ptr,
                            points[0].size(),
                            ys_ptr,
                            points[1].size(),
                            zs_ptr,
                            points[2].size(),
                            values_ptr,
                            &interp_points_ptr[index * num_dims],
                            &out[index],
                            index + stride < num_elements ? stride : num_elements - index
                        )
                    );
                }
                for (auto &future : tasks) {
                    std::move(future);
                }
            }
        } else {
            std::vector<slice<double>> grid;
            for (auto axis : points) {
                auto info = axis.request();
                grid.push_back(slice<double> {
                    (size_t) info.shape[0],
                    (double *) info.ptr
                });
            }
            slice<double> values_slice = {
                values_info.size / sizeof(double),
                values_ptr
            };
            slice<double> interpolation_points_slice = {
                values_info.size / sizeof(double),
                interp_points_ptr
            };
            slice<double> out_slice = {num_elements, out};

            interpolate(
                grid,
                values_slice,
                interpolation_points_slice,
                out_slice
            );
        }


        py::capsule free_when_done(out, [](void *f) {
            double *out = reinterpret_cast<double *>(f);
            delete[] out;
        });

        return py::array_t<double>(
            {num_elements}, // Shape
            {sizeof(double)}, // Strides
            out, // the data pointer
            free_when_done
        ); // numpy array references this parent
    },
    R"pbdoc(
        Linear interpolator in any dimension. Arguments are similar to
        scipy.interpolate.RegularGridInterpolator
    )pbdoc",
    py::arg("points"), py::arg("values"), py::arg("interp_points"), py::arg("max_threads") = 8
  );
}
