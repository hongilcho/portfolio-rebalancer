import streamlit as st

def num_to_kr_mixed(num):
    if not num or num == 0:
        return "0원"
    num = int(num)
    places = ["", "십", "백", "천"]
    units = ["", "만", "억", "조", "경"]
    
    result = ""
    num_str = str(num)
    chunks = []
    while len(num_str) > 0:
        chunks.append(num_str[-4:])
        num_str = num_str[:-4]
        
    for i, chunk in enumerate(chunks):
        if int(chunk) == 0:
            continue
        
        chunk_res = ""
        for j, digit_char in enumerate(chunk[::-1]):
            d = int(digit_char)
            if d > 0:
                chunk_res = f"{d}{places[j]}" + chunk_res
        
        result = chunk_res + units[i] + " " + result
        
    return result.replace("  ", " ").strip() + "원"

def format_usd_label(usd_val):
    if not usd_val or float(usd_val) == 0.0:
        return "0 USD (약 0원)"
    usd_val = float(usd_val)
    rate = st.session_state.get('usd_krw', 1350.0)
    krw_val = usd_val * rate
    return f"{usd_val:,.2f} USD (약 {num_to_kr_mixed(krw_val)})"
