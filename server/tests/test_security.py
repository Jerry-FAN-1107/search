import jwt
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    create_refresh_token,
    decode_refresh_token,
)

def test_verify_password_ok_and_wrong():
    password = "zheshiyigemima"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True
    wrong_password = "cuowumima"
    assert verify_password(wrong_password, hashed) is False


def test_password_is_hashed_not_plain():
    password = "zheshiyigemima"
    hashed = hash_password(password)
    assert password != hashed
    hashed_again = hash_password(password)
    assert hashed != hashed_again

def test_access_token_roundtrip():
    user_id = 123456
    access_token = create_access_token(subject = user_id)
    pyload = decode_access_token(access_token)
    assert pyload["sub"] == str(user_id)
    assert "iat" in pyload
    assert "exp" in pyload
    assert pyload["iat"] < pyload["exp"]




def test_tampered_token_rejected():
    really_token = create_access_token(subject = 123456)
    fake_token = really_token + "1"
    assert really_token != fake_token
    import pytest
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(fake_token)




def test_refresh_token_type_is_checked():
    access_token = create_access_token(subject = 123456)
    import pytest
    with pytest.raises(jwt.InvalidTokenError):
        decode_refresh_token(access_token)
    refresh_token,_,_ = create_refresh_token(subject = 123456)
    pyload = decode_refresh_token(refresh_token)
    assert pyload["type"] == "refresh"
    assert pyload["sub"] == "123456"






def test_verify_password_with_garbage_hash():
    garbage_hashs = [
        "",
        "123",
        "sdadas",
        "$213421#@#&$@("
    ]
    password = "123345"
    for garbage_hash in garbage_hashs:
        assert verify_password(password, garbage_hash) is False