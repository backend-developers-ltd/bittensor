import bittensor
from bittensor._crypto import encrypt_to_file, is_encrypted, decrypt_file, CryptoKeyError
from unittest.mock import MagicMock
import os
import shutil



def init_wallet():
    if os.path.exists('/tmp/pytest'):
        shutil.rmtree('/tmp/pytest')
    
    the_wallet = bittensor.wallet (
        path = '/tmp/pytest',
        name = 'pytest',
        hotkey = 'pytest',
    )
    
    return the_wallet

def check_keys_exists(the_wallet = None):

    # --- test file and key exists
    assert os.path.isfile(the_wallet.coldkeyfile)
    assert os.path.isfile(the_wallet.hotkeyfile)
    assert os.path.isfile(the_wallet.coldkeypubfile)
    
    assert the_wallet._hotkey != None
    assert the_wallet._coldkey != None
    
    # --- test _load_key()
    the_wallet._hotkey = None
    the_wallet._coldkey = None
    the_wallet._coldkeypub = None

    assert the_wallet._load_hotkey() != None
    assert the_wallet._load_coldkey() != None
    assert the_wallet._load_coldkeypub() != None
    
    # --- test prop
    the_wallet._hotkey = None
    the_wallet._coldkey = None
    the_wallet._coldkeypub = None
    
    the_wallet.hotkey
    the_wallet.coldkey
    the_wallet.coldkeypub
    
    assert the_wallet._hotkey != None
    assert the_wallet._coldkey != None
    assert the_wallet._coldkeypub != None

def test_encrypt_and_decrypt():
    init_wallet()
    password = "bit2021SEP"
    file = '/tmp/pytest_test_encrypt_and_decrypt'
    encrypt_to_file("data", password, file)
    assert is_encrypted(file) == True
    data = decrypt_file(password, file)
    assert data == "data"

def test_create_wallet():
    the_wallet = init_wallet().create(coldkey_use_password = False, hotkey_use_password = False)
    check_keys_exists(the_wallet)

def test_create_keys():
    the_wallet = init_wallet()
    the_wallet.create_new_coldkey( use_password=False, overwrite = True )
    the_wallet.create_new_hotkey( use_password=False, overwrite = True )
    check_keys_exists(the_wallet)
    
    the_wallet = init_wallet()
    the_wallet.new_coldkey( use_password=False, overwrite = True )
    the_wallet.new_hotkey( use_password=False, overwrite = True )
    check_keys_exists(the_wallet)

def test_wallet_uri():
    the_wallet = init_wallet()
    the_wallet.create_coldkey_from_uri( uri = "/Alice", use_password=False, overwrite = True )
    the_wallet.create_hotkey_from_uri( uri = "/Alice", use_password=False, overwrite = True )
    check_keys_exists(the_wallet)

def test_wallet_mnemonic_create():
    the_wallet = init_wallet()
    the_wallet.regenerate_coldkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse",  use_password=False, overwrite = True )
    the_wallet.regenerate_coldkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse".split(),  use_password=False, overwrite = True )
    the_wallet.regenerate_hotkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse", use_password=False, overwrite = True )
    the_wallet.regenerate_hotkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse".split(),  use_password=False, overwrite = True )

    the_wallet.regen_coldkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse",  use_password=False, overwrite = True )
    the_wallet.regen_coldkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse".split(),  use_password=False, overwrite = True )
    the_wallet.regen_hotkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse", use_password=False, overwrite = True )
    the_wallet.regen_hotkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse".split(),  use_password=False, overwrite = True )
    check_keys_exists(the_wallet)
    
def test_wallet_uri():
    the_wallet = init_wallet()
    the_wallet.create_coldkey_from_uri( uri = "/Alice", use_password=False, overwrite = True )
    the_wallet.create_hotkey_from_uri( uri = "/Alice", use_password=False, overwrite = True )
    check_keys_exists(the_wallet)

def test_wallet_mnemonic_create():
    the_wallet = init_wallet()
    the_wallet.regenerate_coldkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse",  use_password=False, overwrite = True )
    the_wallet.regenerate_coldkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse".split(),  use_password=False, overwrite = True )
    the_wallet.regenerate_hotkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse", use_password=False, overwrite = True )
    the_wallet.regenerate_hotkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse".split(),  use_password=False, overwrite = True )
    check_keys_exists(the_wallet)

    the_wallet = init_wallet()
    the_wallet.regen_coldkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse",  use_password=False, overwrite = True )
    the_wallet.regen_coldkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse".split(),  use_password=False, overwrite = True )
    the_wallet.regen_hotkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse", use_password=False, overwrite = True )
    the_wallet.regen_hotkey( mnemonic = "solve arrive guilt syrup dust sea used phone flock vital narrow endorse".split(),  use_password=False, overwrite = True )
    check_keys_exists(the_wallet)

def test_wallet_is_registered():
    the_wallet = init_wallet().create(coldkey_use_password = False, hotkey_use_password = False)
    the_wallet.is_registered = MagicMock(return_value = True)
    the_wallet.register( email = 'fake@email.com')
    check_keys_exists(the_wallet)
