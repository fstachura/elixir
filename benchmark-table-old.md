| Command | Mean [s] | Min [s] | Max [s] | Relative |
|:---|---:|---:|---:|---:|
| `ELIXIR_THREADING=1 python3 -m elixir.update` | 144.576 ± 0.640 | 143.854 | 145.071 | 1.02 ± 0.01 |
| ` ELIXIR_CACHE=1 python3 -m elixir.update` | 141.264 ± 2.086 | 138.862 | 142.617 | 1.00 ± 0.01 |
| `python3 -m elixir.update` | 142.201 ± 0.926 | 141.242 | 143.090 | 1.01 ± 0.01 |
| `python3 -m elixir.non_gen_update` | 141.197 ± 0.348 | 140.795 | 141.401 | 1.00 |
