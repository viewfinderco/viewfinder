# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Add functionality to dump stack trace on SIGUSR1 for all python
processes.
"""

import signal
import traceback

signal.signal(signal.SIGUSR1, lambda sig, stack: traceback.print_stack(stack))
