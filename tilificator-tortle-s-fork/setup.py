#!/usr/bin/env python

from distutils.core import setup,Extension
module1 = Extension('c_tile',sources=['c_tile.c'])
setup(  name = 'c_tile',
        version = '1.0',
        description = 'Library of optimized tile functions',
        ext_modules = [module1])
extra_compile_args = ["-O3"]  # You could put "-O4" etc. here.
