| Command | Mean [s] | Min [s] | Max [s] | Relative |
|:---|---:|---:|---:|---:|
| `python3 -m elixir.file_update` | 135.217 ± 5.812 | 131.667 | 141.924 | 1.00 |
| ` ELIXIR_THREADING=1 python3 -m elixir.update` | 138.974 ± 2.734 | 137.364 | 142.130 | 1.03 ± 0.05 |
| ` ELIXIR_CACHE=1 python3 -m elixir.update` | 138.750 ± 0.886 | 137.912 | 139.678 | 1.03 ± 0.04 |
| `python3 -m elixir.update` | 139.629 ± 1.779 | 138.419 | 141.672 | 1.03 ± 0.05 |
| `python3 -m elixir.non_gen_update` | 141.075 ± 2.409 | 138.323 | 142.804 | 1.04 ± 0.05 |
