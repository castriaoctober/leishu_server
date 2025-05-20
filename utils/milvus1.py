# 步骤一：滑动窗口 + 单句向量进行向量化
# 不用加入到前端代码里，步骤一纯属于后端
import pymysql
import numpy as np
import re
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType
from sentence_transformers import models, SentenceTransformer

# 连接 Milvus 和 MySQL
connections.connect("default", host="localhost", port="19530")

db_connection = pymysql.connect(
    host="localhost",
    user="root",
    password="Leishu2025!",  # 输入 MySQL 密码
    database="leishu_yongle",
    charset="utf8mb4"
)

# 定义集合（表）
collections = {
    "one_sentence": "yongle_1",
    "two_sentences": "yongle_2",
    "three_sentences": "yongle_3",
    "four_sentences": "yongle_4"
}

# 创建 Milvus 集合的函数
def create_collection(name):
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="fulltext_id", dtype=DataType.INT64),
        FieldSchema(name="sentence", dtype=DataType.VARCHAR, max_length=1000),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768)
    ]
    schema = CollectionSchema(fields, description=f"{name} 向量数据库")
    return Collection(name=name, schema=schema)

# 创建集合
milvus_collections = {key: create_collection(value) for key, value in collections.items()}

# 加载 BERT-ancient-chinese 模型
model_name = "Jihuai/bert-ancient-chinese"
word_embedding_model = models.Transformer(model_name)
pooling_model = models.Pooling(
    word_embedding_model.get_word_embedding_dimension(),
    pooling_mode_mean_tokens=True
)
model = SentenceTransformer(modules=[word_embedding_model, pooling_model])

# 向量归一化函数
def normalize_vector(vector):
    norm = np.linalg.norm(vector)
    return (vector / norm).tolist() if norm != 0 else vector

# 句子分割函数（保留标点符号）
def segment_text_fixed(text):
    sentences = []
    temp_sentence = ""
    
    for char in text:
        temp_sentence += char  # 添加当前字符
        
        # 如果当前字符是标点符号，则存储（保留标点）
        if char in "，。":
            sentences.append(temp_sentence.strip())  # 去除首尾空格后添加
            temp_sentence = ""  # 开始新的句子

    if temp_sentence:  # 如果有剩余句子，则添加
        sentences.append(temp_sentence.strip())
    
    return sentences  # 保留最后的 `。`

# 从 MySQL 获取数据
def get_texts_from_mysql():
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT full_text_id, full_text FROM full_text_1")
        rows = cursor.fetchall()
    return rows  # [(fulltext_id, "古文段落")]

# 应用滑动窗口
def apply_sliding_window(sentences, window_size):
    """使用滑动窗口将句子组合为 window_size 大小的片段"""
    if len(sentences) < window_size:
        return []
    return ["".join(sentences[i:i+window_size]) for i in range(len(sentences) - window_size + 1)]

# 主处理逻辑
texts = get_texts_from_mysql()

for fulltext_id, paragraph in texts:
    split_sentences = segment_text_fixed(paragraph)  # 句子分割

    if len(split_sentences) == 0:
        continue  # 没有有效句子，跳过

    # 按不同的窗口大小创建句子组合
    sentence_windows_dict = {
        "one_sentence": split_sentences,  # 单句，直接使用分割后的结果
        "two_sentences": apply_sliding_window(split_sentences, 2),
        "three_sentences": apply_sliding_window(split_sentences, 3),
        "four_sentences": apply_sliding_window(split_sentences, 4)
    }

    # 对每个滑动窗口结果进行向量化并存储
    for collection_name, sentence_windows in sentence_windows_dict.items():
        if len(sentence_windows) > 0:
            target_collection = milvus_collections[collection_name]

            # 执行向量化
            sentence_vectors = model.encode(sentence_windows, convert_to_numpy=True)
            sentence_vectors = [normalize_vector(vec) for vec in sentence_vectors]

            # 存储到 Milvus
            target_collection.insert([[fulltext_id] * len(sentence_windows), sentence_windows, sentence_vectors])

# 数据存储完成后刷新
for col in milvus_collections.values():
    col.flush()

# 断开 Milvus 连接
connections.disconnect("default")
db_connection.close()

print("单句和滑动窗口句子向量已全部存储完成！")
# 4月26日实验结果：需要70分钟
