#!/bin/bash

python3 -m cProfile -o /usr/local/elixir/profiles/$RANDOM.prof $1
