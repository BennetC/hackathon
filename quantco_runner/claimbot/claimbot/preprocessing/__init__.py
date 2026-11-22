"""Preparing the data: decrypt the case archive, read the files, parse the invoice.

    archive.py  find the zip for a game, check the key, decrypt it safely
    case.py     build a Case (policy, damage report, invoice text, lines, photos)
    invoice.py  PDF text extraction and invoice line parsing
    images.py   downscale photos before they are sent to a model
"""

from claimbot.preprocessing.archive import decrypt, expected_zip, find_zip_for_key, key_opens
from claimbot.preprocessing.case import load_case

__all__ = ["decrypt", "expected_zip", "find_zip_for_key", "key_opens", "load_case"]
