import torch
from torchvision import models, transforms
from PIL import Image
import pandas as pd
import requests
from tqdm import tqdm
import numpy as np

# ✅ 썸네일 URL 데이터 불러오기
df = pd.read_csv("youtube_videos_20250510.csv")  # 본인 파일 경로
thumbnail_urls = df['썸네일'].tolist()

# ✅ ResNet50 모델 불러오기 (사전학습된 가중치, 마지막 FC 제외)
resnet = models.resnet50(pretrained=True)
resnet = torch.nn.Sequential(*(list(resnet.children())[:-1]))
resnet.eval()

# ✅ 이미지 전처리 파이프라인
preprocess = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std =[0.229, 0.224, 0.225]
    )
])

# ✅ 썸네일 이미지 → 벡터 추출 함수
def extract_thumbnail_vector(url):
    try:
        img = Image.open(requests.get(url, timeout=5, stream=True).raw).convert('RGB')
        img_tensor = preprocess(img).unsqueeze(0)
        with torch.no_grad():
            vec = resnet(img_tensor).squeeze().numpy()  # (2048,)
        return vec
    except Exception as e:
        print(f"실패: {url} | {e}")
        return np.zeros(2048)  # 실패 시 0벡터 대체

# ✅ 전체 썸네일 벡터화
thumbnail_vectors = []
for url in tqdm(thumbnail_urls, desc="썸네일 벡터화 중"):
    thumbnail_vectors.append(extract_thumbnail_vector(url))

thumbnail_vectors = np.array(thumbnail_vectors)  # (N, 2048)

# ✅ 저장
np.save("thumbnail_vectors.npy", thumbnail_vectors)  # .npy 파일
pd.DataFrame(thumbnail_vectors).to_csv("thumbnail_vectors.csv", index=False)  # .csv 파일