"""
航天发动机热试车数据分析 Web Demo

运行方式：
    source /opt/miniconda3/etc/profile.d/conda.sh && conda activate gy_pytorch
    streamlit run app.py --server.port 8501

    浏览器访问：http://localhost:8501
    若远程服务器则替换 localhost 为服务器 IP
"""
import streamlit as st
from pathlib import Path
from PIL import Image

st.set_page_config(
    page_title="热试车数据分析",
    page_icon="🚀",
    layout="wide",
)

# ---------------------------------------------------------------------------
# 侧边栏
# ---------------------------------------------------------------------------
st.sidebar.title("🚀 航天发动机热试车数据分析")
st.sidebar.markdown("---")
st.sidebar.markdown("### 分析模块")
st.sidebar.markdown("- 压力异常点检测（待实现）")
st.sidebar.markdown("- 熄火过程压力分布")
st.sidebar.markdown("---")
st.sidebar.caption("环境：gy_pytorch | GPU：cuda:6,7")

# ---------------------------------------------------------------------------
# 主页面
# ---------------------------------------------------------------------------
st.title("🚀 航天发动机热试车数据分析")
st.markdown("基于大模型 Agent 的发动机热试车数据智能分析 Demo")

tab1, tab2 = st.tabs(["📊 已有分析结果", "🔍 压力异常点检测（待实现）"])

with tab1:
    st.header("熄火过程压力分析")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("压力-时间曲线")
        img_path_1 = Path(__file__).parent / "results_png" / "blow.png"
        if img_path_1.exists():
            st.image(str(img_path_1), use_container_width=True)
        else:
            st.warning(f"图片不存在：{img_path_1}")

    with col2:
        st.subheader("流道压力分布")
        img_path_2 = Path(__file__).parent / "results_png" / "流道压力-01.png"
        if img_path_2.exists():
            st.image(str(img_path_2), use_container_width=True)
        else:
            st.warning(f"图片不存在：{img_path_2}")

with tab2:
    st.info("压力异常点检测模块正在开发中，敬请期待。")
    st.markdown("""
    ### 计划功能
    1. 上传 txt 数据文件
    2. 自动解析压力数据列
    3. 3σ 方法检测异常点
    4. Plotly 交互式图表（异常点红色标注）
    5. Claude API 分析异常统计结果
    """)
