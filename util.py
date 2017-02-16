from Crypto import Random
from Crypto.Cipher import ARC4
from Crypto.Cipher import PKCS1_v1_5
from Crypto.Hash import SHA
from Crypto.PublicKey import RSA


# php openssl_(seal|open)
# http://php.net/manual/en/function.openssl-seal.php (User notes)
#
# example usage:
# sealed, ekey = openssl_seal('Hello wild world', open('key.pub').read())
# print openssl_open(sealed, ekey, open('key.pem').read())

def openssl_seal(plain_data, pub_key):
    # 1. Generate a random key
    nonce = Random.new().read(16)
    rnd_key = SHA.new(nonce).digest()
    # 2. Encrypt the data symmetrically with RC4 using the random key
    rc4 = ARC4.new(rnd_key)
    sealed_data = rc4.encrypt(plain_data)
    # 3. Encrypt the random key itself with RSA using the public key / certificate
    rsa = RSA.importKey(pub_key, None)
    pkcs = PKCS1_v1_5.new(rsa)
    env_key = pkcs.encrypt(rnd_key)
    # 4. Returns the encrypted data and the encrypted key
    return sealed_data, env_key


def openssl_open(sealed_data, env_key, priv_key):
    # 1. Decrypt the key using RSA and your private key
    rsa = RSA.importKey(priv_key, None)
    size = SHA.digest_size
    sentinel = Random.new().read(15 + size)
    pkcs = PKCS1_v1_5.new(rsa)
    d_env_key = pkcs.decrypt(env_key, sentinel)
    # 2. Decrypt the data using RC4 and the decrypted key
    rc4 = ARC4.new(d_env_key)
    return rc4.decrypt(sealed_data)

# TODO: md5sum_match, __str_to_epoch, __epoch_to_str, ... should be in this module.
