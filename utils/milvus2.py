# 步骤二：生成索引
# 不用加入到前端代码里，步骤二纯属于后端
from pymilvus import Collection, connections

connections.connect("default", host="localhost", port="19530")

yongle_collections = ["yongle_1", "yongle_2", "yongle_3", "yongle_4"]

index_params = {
    "metric_type": "COSINE",  # Milvus 内部会转换为 IP
    "index_type": "HNSW",
    "params": {
        "M": 16,  # HNSW 图中每个节点最大连接数（值越大，准确率越高，速度越慢）
        "efConstruction": 500  # 构建索引时的搜索深度（值越大，准确率越高，速度越慢）
    }
}

# 遍历每个集合进行索引创建
for collection_name in yongle_collections:
    print(f"\n[INFO] 集合 {collection_name} 开始创建索引...")
    
    collection = Collection(collection_name)

    # 如果已有索引，则先删除（避免冲突）
    if collection.has_index():
        print(f"[INFO] {collection_name} 存在旧索引，正在删除...")
        collection.drop_index()

    # 创建新的索引
    collection.create_index(field_name="embedding", index_params=index_params)

    # 加载集合到内存，准备搜索
    collection.load()

    print(f"[SUCCESS] {collection_name} 索引创建并加载完成。")

print("\n✅ 所有 Yongle 集合索引已成功创建！")
