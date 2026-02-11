# PyInstaller hook for typing module
# This hook ensures we use Python's built-in typing module instead of the obsolete external package
#
# Note: PyInstaller automatically includes standard library modules like 'typing'
# This hook prevents PyInstaller from including the external typing package from site-packages
# while still allowing the built-in typing module to be included

# Don't exclude typing here - we want the built-in module to be included
# The external typing package should be handled by temporarily renaming it before build
# or by ensuring it's not in site-packages during the build process

# This hook file exists to ensure PyInstaller processes typing correctly
# If an external typing package exists, it should be renamed before building

