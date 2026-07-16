import os
from h4_debug.handlers import handle_image

class Args:
    mode = "Normal"
    port = 8008

handle_image('test.png', ['h4-debug', 'test.png'], os.environ.copy(), Args())
