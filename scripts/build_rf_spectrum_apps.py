#!/usr/bin/env python3
"""Build the next complete Watch candidate; RF spectrum is the default profile."""
from build_current_apps import main

if __name__ == '__main__':
    main(default_profile='rf-spectrum')
