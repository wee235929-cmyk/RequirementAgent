"""
Mermaid 图表渲染全类型测试脚本

测试 deep research 流程中 _fix_mermaid_syntax + _try_render_with_fix 的完整渲染链路。
覆盖所有 Mermaid 图表类型，中文、英文各一张，共 20 张图。

用法：
    python tests/test_mermaid_all_types.py
"""
import sys
import os
from pathlib import Path

# 添加项目路径，直接导入 report_generator 模块以避免 research/__init__.py 拉入 langchain 等重依赖
src_dir = str(Path(__file__).parent.parent / "src")
sys.path.insert(0, src_dir)

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "report_generator",
    os.path.join(src_dir, "research", "report_generator.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
PDFReportGenerator = _mod.PDFReportGenerator


# ============================================================
# 测试用例：10 种图表类型 × 2 种语言 = 20 张图
# ============================================================

TEST_CASES = [
    # ---- 1. Flowchart ----
    {
        "name": "Flowchart (EN)",
        "code": """flowchart TD
    A[User Request] --> B{Valid Input?}
    B -->|Yes| C[Process Data]
    B -->|No| D[Show Error]
    C --> E[Generate Report]
    E --> F[Send Response]
    D --> G[Log Warning]
    G --> B"""
    },
    {
        "name": "Flowchart (CN)",
        "code": """flowchart TD
    A[用户请求] --> B{输入有效?}
    B -->|是| C[处理数据]
    B -->|否| D[显示错误]
    C --> E[生成报告]
    E --> F[返回响应]
    D --> G[记录警告]
    G --> B"""
    },

    # ---- 2. Sequence Diagram ----
    {
        "name": "Sequence Diagram (EN)",
        "code": """sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Database
    User->>Frontend: Submit Query
    Frontend->>Backend: API Request
    Backend->>Database: SQL Query
    Database-->>Backend: Result Set
    Backend-->>Frontend: JSON Response
    Frontend-->>User: Display Results"""
    },
    {
        "name": "Sequence Diagram (CN)",
        "code": """sequenceDiagram
    participant 用户
    participant 前端
    participant 后端
    participant 数据库
    用户->>前端: 提交查询
    前端->>后端: API请求
    后端->>数据库: SQL查询
    数据库-->>后端: 返回结果
    后端-->>前端: JSON响应
    前端-->>用户: 展示结果"""
    },

    # ---- 3. Class Diagram ----
    {
        "name": "Class Diagram (EN)",
        "code": """classDiagram
    class Vehicle {
        +String brand
        +int speed
        +start()
        +stop()
    }
    class Car {
        +int doors
        +drive()
    }
    class Truck {
        +int payload
        +haul()
    }
    Vehicle <|-- Car
    Vehicle <|-- Truck"""
    },
    {
        "name": "Class Diagram (CN)",
        "code": """classDiagram
    class 车辆 {
        +String 品牌
        +int 速度
        +启动()
        +停止()
    }
    class 轿车 {
        +int 车门数
        +驾驶()
    }
    class 卡车 {
        +int 载重量
        +运输()
    }
    车辆 <|-- 轿车
    车辆 <|-- 卡车"""
    },

    # ---- 4. State Diagram ----
    {
        "name": "State Diagram (EN)",
        "code": """stateDiagram-v2
    [*] --> Idle
    Idle --> Processing : Start Task
    Processing --> Success : Complete
    Processing --> Error : Failure
    Success --> Idle : Reset
    Error --> Idle : Retry
    Success --> [*]"""
    },
    {
        "name": "State Diagram (CN)",
        "code": """stateDiagram-v2
    [*] --> 空闲
    空闲 --> 处理中 : 开始任务
    处理中 --> 成功 : 完成
    处理中 --> 失败 : 出错
    成功 --> 空闲 : 重置
    失败 --> 空闲 : 重试
    成功 --> [*]"""
    },

    # ---- 5. ER Diagram ----
    {
        "name": "ER Diagram (EN)",
        "code": """erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ LINEITEM : contains
    PRODUCT ||--o{ LINEITEM : includes
    CUSTOMER {
        string name
        string email
        int age
    }
    ORDER {
        int orderNumber
        date orderDate
        float total
    }
    PRODUCT {
        string title
        float price
    }"""
    },
    {
        "name": "ER Diagram (CN)",
        "code": """erDiagram
    客户 ||--o{ 订单 : 下单
    订单 ||--|{ 订单明细 : 包含
    产品 ||--o{ 订单明细 : 涉及
    客户 {
        string 姓名
        string 邮箱
        int 年龄
    }
    订单 {
        int 订单号
        date 下单日期
        float 总金额
    }
    产品 {
        string 名称
        float 价格
    }"""
    },

    # ---- 6. Gantt Chart ----
    {
        "name": "Gantt Chart (EN)",
        "code": """gantt
    title Project Development Timeline
    dateFormat YYYY-MM-DD
    section Planning
        Requirements Analysis : 2024-01-01, 30d
        Architecture Design   : 2024-01-15, 20d
    section Development
        Backend Development   : 2024-02-01, 60d
        Frontend Development  : 2024-02-15, 45d
    section Testing
        Integration Testing   : 2024-04-01, 20d
        User Acceptance       : 2024-04-15, 15d"""
    },
    {
        "name": "Gantt Chart (CN)",
        "code": """gantt
    title 项目开发时间线
    dateFormat YYYY-MM-DD
    section 规划阶段
        需求分析 : 2024-01-01, 30d
        架构设计 : 2024-01-15, 20d
    section 开发阶段
        后端开发 : 2024-02-01, 60d
        前端开发 : 2024-02-15, 45d
    section 测试阶段
        集成测试 : 2024-04-01, 20d
        用户验收 : 2024-04-15, 15d"""
    },

    # ---- 7. Pie Chart ----
    {
        "name": "Pie Chart (EN)",
        "code": """pie title Market Share Distribution
    "Product A" : 35
    "Product B" : 25
    "Product C" : 20
    "Product D" : 12
    "Others" : 8"""
    },
    {
        "name": "Pie Chart (CN)",
        "code": """pie title 市场份额分布
    "产品A" : 35
    "产品B" : 25
    "产品C" : 20
    "产品D" : 12
    "其他" : 8"""
    },

    # ---- 8. Mindmap ----
    {
        "name": "Mindmap (EN)",
        "code": """mindmap
  root((AI Technology))
    Machine Learning
      Supervised
      Unsupervised
      Reinforcement
    Deep Learning
      CNN
      RNN
      Transformer
    Applications
      NLP
      Computer Vision
      Robotics"""
    },
    {
        "name": "Mindmap (CN)",
        "code": """mindmap
  root((人工智能技术))
    机器学习
      监督学习
      无监督学习
      强化学习
    深度学习
      卷积神经网络
      循环神经网络
      Transformer
    应用领域
      自然语言处理
      计算机视觉
      机器人技术"""
    },

    # ---- 9. Timeline ----
    {
        "name": "Timeline (EN)",
        "code": """timeline
    title History of Computing
    section Early Era
        1940 : First Electronic Computer
        1950 : Commercial Mainframes
    section Personal Computing
        1975 : Altair 8800
        1984 : Macintosh Launch
    section Internet Age
        1991 : World Wide Web
        2007 : iPhone Release"""
    },
    {
        "name": "Timeline (CN)",
        "code": """timeline
    title 计算机发展史
    section 早期时代
        1940 : 第一台电子计算机
        1950 : 商用大型机
    section 个人电脑时代
        1975 : Altair 8800
        1984 : Macintosh发布
    section 互联网时代
        1991 : 万维网诞生
        2007 : iPhone发布"""
    },

    # ---- 10. Quadrant Chart ----
    {
        "name": "Quadrant Chart (EN)",
        "code": """quadrantChart
    title Technology Evaluation
    x-axis Low Cost --> High Cost
    y-axis Low Impact --> High Impact
    "Cloud Native" : [0.3, 0.8]
    "Blockchain" : [0.7, 0.4]
    "AI/ML" : [0.6, 0.9]
    "IoT" : [0.4, 0.6]
    "Quantum" : [0.9, 0.7]"""
    },
    {
        "name": "Quadrant Chart (CN)",
        "code": """quadrantChart
    title 技术评估矩阵
    x-axis "低成本" --> "高成本"
    y-axis "低影响" --> "高影响"
    "云原生" : [0.3, 0.8]
    "区块链" : [0.7, 0.4]
    "人工智能" : [0.6, 0.9]
    "物联网" : [0.4, 0.6]
    "量子计算" : [0.9, 0.7]"""
    },
]


def main():
    print("=" * 70)
    print("  Mermaid 全类型渲染测试")
    print("  调用 PDFReportGenerator._fix_mermaid_syntax + _try_render_with_fix")
    print("=" * 70)

    generator = PDFReportGenerator()
    output_dir = generator.image_cache_dir / "mermaid_test"
    output_dir.mkdir(exist_ok=True)

    results = {"success": [], "failed": []}
    total = len(TEST_CASES)

    for i, tc in enumerate(TEST_CASES, 1):
        name = tc["name"]
        code = tc["code"]
        print(f"\n[{i}/{total}] {name}")
        print("-" * 50)

        # Step 1: 语法修复（含 CJK 替换）
        fixed_code = generator._fix_mermaid_syntax(code)
        has_cjk = any('\u4e00' <= ch <= '\u9fff' for ch in fixed_code)
        if has_cjk:
            print(f"  ⚠ WARNING: CJK characters remain after fix!")
        
        # 显示修复后的代码（截取前 5 行）
        preview_lines = fixed_code.split('\n')[:5]
        for line in preview_lines:
            print(f"  | {line}")
        if len(fixed_code.split('\n')) > 5:
            print(f"  | ... ({len(fixed_code.split(chr(10)))} lines total)")

        # Step 2: 渲染
        img_data = generator._try_render_with_fix(code)

        if img_data:
            # 保存图片
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(img_data))
            if img.mode in ('RGBA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[3])
                else:
                    background.paste(img)
                img = background

            safe_name = name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
            img_path = output_dir / f"{i:02d}_{safe_name}.png"
            img.save(str(img_path), "PNG", optimize=True)

            print(f"  ✅ SUCCESS  |  Size: {img.size[0]}x{img.size[1]}  |  File: {img_path.name}")
            results["success"].append(name)
        else:
            print(f"  ❌ FAILED   |  All render methods failed")
            results["failed"].append(name)

    # ============================================================
    # 汇总
    # ============================================================
    print("\n" + "=" * 70)
    print("  测试汇总")
    print("=" * 70)
    print(f"  总计:   {total}")
    print(f"  成功:   {len(results['success'])}  ✅")
    print(f"  失败:   {len(results['failed'])}  ❌")
    print(f"  成功率: {len(results['success'])/total*100:.1f}%")

    if results["failed"]:
        print(f"\n  失败项:")
        for name in results["failed"]:
            print(f"    - {name}")

    if results["success"]:
        print(f"\n  图片保存目录: {output_dir}")

    print("=" * 70)
    return len(results["failed"]) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
