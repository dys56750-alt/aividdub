import streamlit as st
import os
import re
import ssl
import subprocess
import glob
import shutil
import base64
import requests
import urllib3
from pydub import AudioSegment
import yt_dlp
from google import genai

# Setup SSL & Warnings
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="Khmer Dubbing Studio Pro", layout="wide")

# Custom UI Styling
st.markdown("""
    <style>
    div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea {
        background-color: #121214 !important;
        color: #FFFFFF !important;
        font-size: 15px !important;
        border: 1px solid #333333 !important;
    }
    div.stButton > button[kind="primary"] {
        background-color: #28a745 !important;
        border-color: #28a745 !important;
        color: white !important;
        font-weight: bold !important;
    }
    .sub-card {
        background: #18181c;
        border: 1px solid #2e2e38;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 12px;
    }
    </style>
""", unsafe_allow_html=True)

# File Paths
CACHE_SCRIPT_FILE = "cached_script.txt"
video_input_path = "original_video.mp4"
extracted_mp3_path = "extracted_audio.mp3"
raw_khmer_audio = "raw_khmer_audio.mp3"
final_video_no_sub = "final_dubbed_audio_only.mp4"

def get_dir_size_mb():
    total_size = 0
    for dirpath, dirnames, filenames in os.walk('.'):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)

def hard_reset_all():
    files_to_delete = [
        CACHE_SCRIPT_FILE, video_input_path, extracted_mp3_path, 
        raw_khmer_audio, final_video_no_sub,
        "temp_dl_video.mp4", "temp_dl_audio.mp3", "t_raw_vid.mp4", "t_raw_aud.mp3"
    ]
    for f in files_to_delete:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass
            
    for pattern in ["*.mp3", "*.wav", "*.mp4", "*.srt", "*.ass"]:
        for f in glob.glob(pattern):
            try: os.remove(f)
            except Exception: pass

    for p in glob.glob("temp_*") + glob.glob("raw_*") + glob.glob("t_raw_*") + ["temp_processing", "__pycache__"]:
        if os.path.exists(p):
            try:
                if os.path.isdir(p): shutil.rmtree(p, ignore_errors=True)
                else: os.remove(p)
            except Exception: pass
            
    st.session_state.clear()

st.title("🎬 Khmer Dubbing Studio Pro")

# Storage Info Bar
col_info, col_reset = st.columns([2.5, 1.5])
with col_info:
    st.info("💡 ដំណើរការ៖ ១. បញ្ចូលវីដេអូ ➔ ២. Gemini បកប្រែ Script ➔ ៣. ផ្ទៀងផ្ទាត់ & កែសម្រួល ➔ ៤. Render")
with col_reset:
    used_mb = get_dir_size_mb()
    st.metric(label="💾 Disk Usage", value=f"{used_mb:.1f} MB")
    if st.button("🗑️ Reset Storage", type="secondary", use_container_width=True):
        hard_reset_all()
        st.success("✅ បានសម្អាតទំហំផ្ទុកជោគជ័យ!")
        st.rerun()

st.divider()

# 1. API Key
st.subheader("🔑 ១. បញ្ចូល Gemini API Key")
gemini_key = st.text_input("🔑 Gemini API Key:", type="password", value="")

st.divider()

def has_audio_stream(file_path):
    try:
        chk = subprocess.run(
            ["ffprobe", "-i", file_path, "-show_streams", "-select_streams", "a", "-loglevel", "error"],
            capture_output=True, text=True
        )
        return bool(chk.stdout.strip())
    except Exception:
        return False

def get_clean_tiktok_url(url):
    try:
        session = requests.Session()
        res = session.get(url, allow_redirects=True, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        return res.url.split('?')[0]
    except Exception:
        return url

def download_video_all(url, out_path):
    url = url.strip()
    for f in [out_path, "t_raw_vid.mp4", "t_raw_aud.mp3"]:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass

    # 1. TikTok
    if "tiktok.com" in url.lower() or "vt.tiktok" in url.lower():
        real_url = get_clean_tiktok_url(url)
        try:
            api_url = "https://www.tikwm.com/api/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
                'Accept': 'application/json'
            }
            res = requests.post(api_url, headers=headers, data={'url': real_url, 'count': 12, 'cursor': 0, 'web': 1, 'hd': 1}, timeout=15).json()
            if res.get("code") == 0 and "data" in res:
                v_url = res["data"].get("hdplay") or res["data"].get("play") or res["data"].get("wmplay")
                if v_url:
                    if not v_url.startswith("http"):
                        v_url = "https://www.tikwm.com" + ("" if v_url.startswith("/") else "/") + v_url
                    rv = requests.get(v_url, headers={'User-Agent': 'Mozilla/5.0'}, verify=False, timeout=30)
                    with open(out_path, "wb") as f:
                        f.write(rv.content)
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                        return True, "ជោគជ័យតាម TikWM"
        except Exception:
            pass

        try:
            ss_res = requests.post(
                "https://ssstik.io/abc?url=dl",
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
                data={'id': real_url, 'locale': 'en', 'tt': 'none'},
                timeout=15
            ).text
            match = re.search(r'href="(https://[^"]+)" class="[^"]*download_link', ss_res)
            if match:
                dl_link = match.group(1)
                rv = requests.get(dl_link, headers={'User-Agent': 'Mozilla/5.0'}, verify=False, timeout=30)
                with open(out_path, "wb") as f:
                    f.write(rv.content)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                    return True, "ជោគជ័យតាម SSSTik"
        except Exception:
            pass

        return False, "មិនអាចទាញយក TikTok បានទេ!"

    # 2. YouTube / Others
    ydl_opts = {
        'format': 'best[ext=mp4]/bestvideo+bestaudio/best',
        'outtmpl': out_path,
        'nocheckcertificate': True,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        },
        'extractor_args': {
            'youtube': {'player_client': ['android', 'ios', 'web']}
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return True, "ជោគជ័យ"
    except Exception as e:
        return False, f"កំហុសទាញយក៖ {e}"

    return False, "មិនអាចទាញយកបានទេ សូម Upload File MP4"

def generate_khmer_dub_srt(audio_path: str, api_key: str, model_name: str = "gemini-3.6-flash") -> str:
    client = genai.Client(api_key=api_key)
    uploaded_audio = client.files.upload(file=audio_path)

    prompt = r"""
Listen to the audio and create a valid SRT for dubbing into Khmer.

Strict Rules:
1. Transcribe speech accurately and translate naturally into Khmer.
2. Accurately detect speaker gender for each subtitle line.
3. Every subtitle line MUST start with exactly one tag:
   (female) = for female voice
   (man) = for male voice
4. Return ONLY valid SRT format. Do not add markdown blocks (no ```srt), explanations, or notes.
5. Provide EVERY dialogue line until the very end of the file.

Example Format:
1
00:00:01,000 --> 00:00:03,500
(female) សួស្តី! តើអ្នកសុខសប្បាយទេ?

2
00:00:03,600 --> 00:00:05,200
(man) បាទ ខ្ញុំសុខសប្បាយទេ។
"""
    response = client.models.generate_content(
        model=model_name,
        contents=[prompt, uploaded_audio],
    )

    try:
        client.files.delete(name=uploaded_audio.name)
    except Exception:
        pass

    raw_text = getattr(response, "text", "").strip()
    cleaned_srt = re.sub(r"^\s*```(?:srt|text)?\s*", "", raw_text, flags=re.I)
    cleaned_srt = re.sub(r"\s*```\s*$", "", cleaned_srt).strip()
    return cleaned_srt

def parse_time_to_ms(t):
    t = t.replace(',', '.').strip()
    p = t.split(':')
    if len(p) == 3: 
        return int((int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])) * 1000)
    elif len(p) == 2: 
        return int((int(p[0]) * 60 + float(p[1])) * 1000)
    elif len(p) == 1:
        return int(float(p[0]) * 1000)
    return 0

def clean_speech_text(text):
    patterns = [
        r'\[\s*(ស្រី|female|woman|girl|f)\s*\]:?',
        r'\(\s*(ស្រី|female|woman|girl|f)\s*\):?',
        r'\[\s*(ប្រុស|male|man|boy|m)\s*\]:?',
        r'\(\s*(ប្រុស|male|man|boy|m)\s*\):?',
        r'^(ស្រី|female|woman|girl|f)\s*[:：\-]\s*',
        r'^(ប្រុស|male|man|boy|m)\s*[:：\-]\s*'
    ]
    cleaned = text
    for pat in patterns:
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE).strip()
    # កម្ចាត់កន្ទុយលេខរៀងដែល Gemini អាចច្រឡំបញ្ចូលនៅចុងឃ្លា (ឧ. "... 71")
    cleaned = re.sub(r'\s+\d{1,4}$', '', cleaned).strip()
    return re.sub(r'^[\[\(].*?[\]\)]\s*[:：]?', '', cleaned).strip()

def parse_srt_to_list(srt_text):
    # Robust SRT parser using regex blocks
    pattern = re.compile(
        r'(?:(\d+)\s*\n)?'
        r'((?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*((?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3})'
        r'[\r\n]+([\s\S]*?)(?=(?:\r?\n\s*\d+\s*\r?\n(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3})|(?:\r?\n\s*(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}\s*-->)|$)',
        re.MULTILINE
    )
    
    items = []
    for match in pattern.finditer(srt_text):
        seq, start_t, end_t, text_block = match.groups()
        full_txt = " ".join([l.strip() for l in text_block.strip().splitlines() if l.strip()])
        if not full_txt:
            continue
            
        tag = "(female)" if any(k in full_txt.lower() for k in ["female", "ស្រី", "(f)", "[ស្រី]"]) else "(man)"
        cleaned_text = clean_speech_text(full_txt)
        
        items.append({
            "seq": seq or str(len(items) + 1),
            "start_raw": start_t.replace('.', ','),
            "end_raw": end_t.replace('.', ','),
            "start": parse_time_to_ms(start_t),
            "end": parse_time_to_ms(end_t),
            "tag": tag,
            "text": cleaned_text
        })
    return items

def generate_and_fit_audio(text, voice, out_path, target_ms):
    temp_raw = f"raw_{out_path}"
    subprocess.run(["edge-tts", "--voice", voice, "--text", text, "--write-media", temp_raw], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.path.exists(temp_raw):
        seg = AudioSegment.from_file(temp_raw)
        actual_ms = len(seg)
        if target_ms <= 0: target_ms = actual_ms
        factor = max(0.6, min(1.8, actual_ms / target_ms))
        if abs(factor - 1.0) > 0.05:
            subprocess.run(["ffmpeg", "-y", "-i", temp_raw, "-filter:a", f"atempo={factor:.2f}", out_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(temp_raw): os.remove(temp_raw)
        else:
            if os.path.exists(out_path): os.remove(out_path)
            os.rename(temp_raw, out_path)

# 2. Video Source
st.subheader("📥 ២. ប្រភពវីដេអូដើម")
input_opt = st.radio("វិធីសាស្ត្របញ្ចូលវីដេអូ៖", ["🔗 URL Link (TikTok/Dailymotion/FB/YouTube)", "📂 Upload File MP4"], key="v_opt")

if input_opt == "🔗 URL Link (TikTok/Dailymotion/FB/YouTube)":
    url_in = st.text_input("🔗 បញ្ចូល Link វីដេអូ៖", placeholder="[https://vt.tiktok.com/](https://vt.tiktok.com/)... ឬ [https://youtube.com/](https://youtube.com/)...")
    if st.button("📥 ទាញយកវីដេអូដើម", type="secondary"):
        if not url_in.strip(): 
            st.error("សូមបញ្ចូល URL!")
        else:
            if os.path.exists(CACHE_SCRIPT_FILE): os.remove(CACHE_SCRIPT_FILE)
            st_box = st.empty()
            st_box.info("⏳ កំពុងទាញយកវីដេអូ...")
            ok, msg = download_video_all(url_in.strip(), video_input_path)
            if ok:
                st_box.success("🎉 ទាញយកវីដេអូជោគជ័យ!")
                st.rerun()
            else: 
                st_box.error(f"❌ {msg}")
else:
    up_v = st.file_uploader("📂 Upload File MP4 វីដេអូដើម", type=["mp4", "mov"])
    if up_v:
        if os.path.exists(CACHE_SCRIPT_FILE): os.remove(CACHE_SCRIPT_FILE)
        with open(video_input_path, "wb") as f: f.write(up_v.read())
        st.success("✅ បាន Upload រួចរាល់!")

if os.path.exists(video_input_path):
    col_vid_del, col_vid_ai = st.columns([1, 3])
    with col_vid_del:
        if st.button("🗑️ លុបវីដេអូនេះ", use_container_width=True):
            if os.path.exists(video_input_path): os.remove(video_input_path)
            st.rerun()
            
    with col_vid_ai:
        if st.button("✨ ប្រើ Gemini 3.6 Flash ស្ដាប់វីដេអូ ➔ បកប្រែជា Khmer SRT", type="primary", use_container_width=True):
            if not gemini_key.strip(): 
                st.error("❌ សូមបញ្ចូល Gemini API Key!")
            else:
                st_box = st.empty()
                st_box.info("⏳ កំពុងបន្សុទ្ធសំឡេង (16kHz Mono)...")
                subprocess.run([
                    "ffmpeg", "-y", "-i", video_input_path,
                    "-vn", "-ar", "16000", "-ac", "1", "-b:a", "128k",
                    extracted_mp3_path
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if not os.path.exists(extracted_mp3_path) or os.path.getsize(extracted_mp3_path) < 1000:
                    st_box.error("❌ មិនអាចទាញយកសំឡេងបានទេ!")
                else:
                    try:
                        st_box.info("✨ Gemini 3.6 Flash កំពុងស្ដាប់ & បកប្រែជាភាសាខ្មែរ...")
                        srt_output = generate_khmer_dub_srt(extracted_mp3_path, gemini_key.strip())
                        with open(CACHE_SCRIPT_FILE, "w", encoding="utf-8") as f: 
                            f.write(srt_output)
                        st_box.success("🎉 Gemini 3.6 Flash បានបកប្រែរួចរាល់ពេញលេញ!")
                        st.rerun()
                    except Exception as e: 
                        st_box.error(f"❌ កំហុស Gemini៖ {e}")

st.divider()

# 3. Interactive Video Player + Editable Subtitle Cards
st.subheader("📝 ៣. ផ្ទៀងផ្ទាត់ & កែសម្រួល Script SRT")

cur_script = open(CACHE_SCRIPT_FILE, 'r', encoding='utf-8').read() if os.path.exists(CACHE_SCRIPT_FILE) else ""

# Video Player with Seek controls
if os.path.exists(video_input_path):
    with open(video_input_path, "rb") as vf:
        video_b64 = base64.b64encode(vf.read()).decode()
    
    player_html = f"""
    <div style="background:#000; padding:10px; border-radius:10px; margin-bottom:15px; border:1px solid #333; text-align:center;">
        <video id="syncPlayer" controls style="width:100%; max-height:420px; border-radius:8px; background:#000;">
            <source src="data:video/mp4;base64,{video_b64}" type="video/mp4">
        </video>
    </div>
    <script>
        function seekVideo(timeSec) {{
            var v = document.getElementById('syncPlayer');
            if (v) {{
                v.currentTime = timeSec;
                v.play();
            }}
        }}
    </script>
    """
    st.components.v1.html(player_html, height=450)

# Subtitle Cards Editor
sub_list = parse_srt_to_list(cur_script) if cur_script.strip() else []

if sub_list:
    st.markdown(f"#### 📋 រកឃើញសរុប **{len(sub_list)} ជួរ**")

    # Save button placed at the top for easy access
    if st.button("💾 រក្សាទុកការកែប្រែ Script ទាំងអស់ (Save Top)", type="primary", key="save_top", use_container_width=True):
        reconstructed_srt = []
        for i, item in enumerate(sub_list):
            tag_val = st.session_state.get(f"tag_{i}", item["tag"])
            txt_val = st.session_state.get(f"txt_{i}", item["text"])
            reconstructed_srt.append(f"{i+1}\n{item['start_raw']} --> {item['end_raw']}\n{tag_val} {txt_val}\n")
        
        final_saved_srt = "\n".join(reconstructed_srt)
        with open(CACHE_SCRIPT_FILE, "w", encoding="utf-8") as f:
            f.write(final_saved_srt)
        st.success("🎉 បានរក្សាទុក Script SRT រួចរាល់!")
        st.rerun()

    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

    # Subtitle Rows Display
    for i, item in enumerate(sub_list):
        gender_icon = "👩 [ស្រី]" if item["tag"] == "(female)" else "👨 [ប្រុស]"
        
        st.markdown(f"""
            <div style="color:#28a745; font-size:16px; font-weight:bold; margin-top:12px; margin-bottom:4px;">
                #{i+1} [{item['start_raw']} ➔ {item['end_raw']}] &nbsp;|&nbsp; {gender_icon}
            </div>
        """, unsafe_allow_html=True)
        
        c_tag, c_txt = st.columns([1, 4])
        with c_tag:
            st.selectbox(
                f"តួអង្គ #{i+1}",
                options=["(man)", "(female)"],
                index=0 if item["tag"] == "(man)" else 1,
                key=f"tag_{i}",
                label_visibility="collapsed"
            )
        with c_txt:
            st.text_input(
                f"អត្ថបទ #{i+1}",
                value=item["text"],
                key=f"txt_{i}",
                label_visibility="collapsed"
            )
        st.markdown("<hr style='margin: 8px 0; border:0; border-top: 1px solid #222;'>", unsafe_allow_html=True)

    # Save button placed at the bottom
    if st.button("💾 រក្សាទុកការកែប្រែ Script ទាំងអស់ (Save Bottom)", type="primary", key="save_bottom", use_container_width=True):
        reconstructed_srt = []
        for i, item in enumerate(sub_list):
            tag_val = st.session_state.get(f"tag_{i}", item["tag"])
            txt_val = st.session_state.get(f"txt_{i}", item["text"])
            reconstructed_srt.append(f"{i+1}\n{item['start_raw']} --> {item['end_raw']}\n{tag_val} {txt_val}\n")
        
        final_saved_srt = "\n".join(reconstructed_srt)
        with open(CACHE_SCRIPT_FILE, "w", encoding="utf-8") as f:
            f.write(final_saved_srt)
        st.success("🎉 បានរក្សាទុក Script SRT រួចរាល់!")
        st.rerun()
else:
    st.info("💡 មិនទាន់មាន Script SRT នៅឡើយទេ។ សូមចុចប៊ូតុងបកប្រែជាមួយ Gemini នៅខាងលើ។")

st.divider()

v_choice = st.selectbox("🎙️ សំឡេងអាន៖", ["🤖 អូតូ (ប្រុស/ស្រី តាម Tag)", "👨 Piseth (ប្រុសសុទ្ធ)", "👩 Sreymom (ស្រីសុទ្ធ)"])

st.divider()

# 4. Step 1: TTS Audio Generation
st.subheader("🔊 ៤. ជំហានទី ១៖ បង្កើតសំឡេង Auto-Sync (TTS)")
if st.button("🎙️ ចាប់ផ្ដើមបង្កើតសំឡេង Auto-Sync (MP3)", type="primary", use_container_width=True):
    fresh_script = open(CACHE_SCRIPT_FILE, 'r', encoding='utf-8').read() if os.path.exists(CACHE_SCRIPT_FILE) else ""
    if not fresh_script.strip(): 
        st.error("សូមបញ្ចូល Script SRT!")
    else:
        parsed_items = parse_srt_to_list(fresh_script)
        total = len(parsed_items)
        st.markdown(f"### 📊 រកឃើញសរុប **{total} ជួរ**")
        
        if total > 0:
            combined = AudioSegment.silent(duration=0)
            current_ms = 0
            prog = st.progress(0)
            status = st.empty()
            
            for idx, it in enumerate(parsed_items):
                status.text(f"⚡ កំពុង Sync ជួរទី {idx+1}/{total}: {it['text'][:25]}...")
                if it["start"] > current_ms:
                    combined += AudioSegment.silent(duration=it["start"] - current_ms)
                    current_ms = it["start"]
                
                v = "km-KH-PisethNeural"
                if "🤖" in v_choice or "អូតូ" in v_choice:
                    if it["tag"] == "(female)":
                        v = "km-KH-SreymomNeural"
                elif "👩" in v_choice:
                    v = "km-KH-SreymomNeural"

                temp_f = f"temp_{idx}.mp3"
                try:
                    generate_and_fit_audio(it["text"], v, temp_f, it["end"] - it["start"])
                    if os.path.exists(temp_f):
                        seg = AudioSegment.from_file(temp_f)
                        combined += seg
                        current_ms += len(seg)
                        os.remove(temp_f)
                except Exception: 
                    pass
                prog.progress(int((idx + 1) / total * 100))
                
            combined.export(raw_khmer_audio, format="mp3")
            status.success(f"🎉 បង្កើតសំឡេង Auto-Sync គ្រប់ {total} ជួររួចរាល់!")
            st.rerun()
        else:
            st.error("❌ មិនអាច Parse SRT បានទេ! សូមពិនិត្យមើលទម្រង់ម៉ោង។")

if os.path.exists(raw_khmer_audio):
    st.audio(raw_khmer_audio, format="audio/mp3")
    with open(raw_khmer_audio, "rb") as af:
        st.download_button("📥 ទាញយក File MP3 សុទ្ធ", af, file_name="khmer_audio_synced.mp3")

st.divider()

# 5. Step 2: Super Fast Render
st.subheader("🎬 ៥. ជំហានទី ២៖ Render វីដេអូ + សំឡេង")

if st.button("🚀 Render Video + Audio Only", type="primary", use_container_width=True):
    if not os.path.exists(video_input_path):
        st.error("❌ មិនទាន់មានវីដេអូដើមទេ!")
    elif not os.path.exists(raw_khmer_audio):
        st.error("❌ សូមចុចបង្កើតសំឡេង (ជំហានទី ៤) ជាមុនសិន!")
    else:
        status_box = st.empty()
        status_box.info("⏳ កំពុង Merge សំឡេងចូលវីដេអូ...")
        
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", video_input_path,
            "-i", raw_khmer_audio,
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            final_video_no_sub
        ]
        subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        status_box.success("🎉 Render វីដេអូ + សំឡេងសុទ្ធ រួចរាល់!")
        st.rerun()

if os.path.exists(final_video_no_sub):
    st.video(final_video_no_sub)
    with open(final_video_no_sub, "rb") as vf1:
        st.download_button("📥 Download Video Final", vf1, file_name="dubbed_video_audio_only.mp4", use_container_width=True)
