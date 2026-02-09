"""
Test script for Mermaid diagram rendering functionality.
Tests both Kroki.io and mermaid.ink rendering methods.
"""
import sys
import os
import io
import re
import hashlib
import zlib
import base64
from pathlib import Path

import requests
from PIL import Image


class MermaidRenderTester:
    """Standalone Mermaid rendering tester (no dependencies on other modules)."""
    
    def __init__(self):
        self.image_cache_dir = Path("reports/image_cache")
        self.image_cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _render_mermaid_via_kroki(self, mermaid_code: str):
        """Render Mermaid code using Kroki.io API."""
        try:
            compressed = zlib.compress(mermaid_code.encode('utf-8'), 9)
            encoded = base64.urlsafe_b64encode(compressed).decode('utf-8')
            
            kroki_url = f"https://kroki.io/mermaid/png/{encoded}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(kroki_url, timeout=30, headers=headers)
            
            if response.status_code == 200:
                return response.content
            
            kroki_post_url = "https://kroki.io/mermaid/png"
            response = requests.post(
                kroki_post_url,
                data=mermaid_code.encode('utf-8'),
                headers={'Content-Type': 'text/plain', 'User-Agent': 'Mozilla/5.0'},
                timeout=30
            )
            response.raise_for_status()
            return response.content
            
        except Exception as e:
            print(f"    Kroki render failed: {e}")
            return None
    
    def _render_mermaid_via_ink(self, mermaid_code: str):
        """Render Mermaid code using mermaid.ink API."""
        try:
            encoded = base64.urlsafe_b64encode(mermaid_code.encode('utf-8')).decode('utf-8')
            mermaid_url = f"https://mermaid.ink/img/{encoded}?scale=3"
            
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(mermaid_url, timeout=30, headers=headers)
            response.raise_for_status()
            return response.content
        except Exception as e:
            print(f"    mermaid.ink render failed: {e}")
            return None
    
    def _process_mermaid_code_blocks(self, content: str) -> str:
        """Process mermaid code blocks in content."""
        mermaid_pattern = re.compile(r'```mermaid\s*([\s\S]*?)\s*```', re.IGNORECASE)
        
        def render_block(match):
            code = match.group(1).strip()
            if not code:
                return ""
            
            img_data = self._render_mermaid_via_kroki(code)
            if not img_data:
                img_data = self._render_mermaid_via_ink(code)
            
            if not img_data:
                return ""
            
            img = Image.open(io.BytesIO(img_data))
            if img.mode in ('RGBA', 'P'):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    bg.paste(img, mask=img.split()[3])
                else:
                    bg.paste(img)
                img = bg
            
            img_hash = hashlib.md5(code.encode()).hexdigest()[:12]
            img_path = self.image_cache_dir / f"mermaid_block_{img_hash}.png"
            img.save(str(img_path), "PNG", optimize=True)
            
            return f"\n[RENDERED_MERMAID_IMAGE:{img_path}|Diagram]\n"
        
        return mermaid_pattern.sub(render_block, content)


generator = MermaidRenderTester()


def test_mermaid_rendering():
    """Test Mermaid diagram rendering with various diagram types."""
    
    test_cases = [
        {
            "name": "Simple Flowchart",
            "code": """flowchart TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Action 1]
    B -->|No| D[Action 2]
    C --> E[End]
    D --> E"""
        },
        {
            "name": "Sequence Diagram",
            "code": """sequenceDiagram
    participant User
    participant System
    participant Database
    
    User->>System: Request Data
    System->>Database: Query
    Database-->>System: Results
    System-->>User: Response"""
        },
        {
            "name": "Class Diagram",
            "code": """classDiagram
    class Animal {
        +String name
        +int age
        +makeSound()
    }
    class Dog {
        +String breed
        +bark()
    }
    class Cat {
        +String color
        +meow()
    }
    Animal <|-- Dog
    Animal <|-- Cat"""
        },
        {
            "name": "State Diagram",
            "code": """stateDiagram-v2
    [*] --> Idle
    Idle --> Processing: Start
    Processing --> Success: Complete
    Processing --> Error: Fail
    Success --> [*]
    Error --> Idle: Retry"""
        },
        {
            "name": "ER Diagram",
            "code": """erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ LINE-ITEM : contains
    PRODUCT ||--o{ LINE-ITEM : includes
    CUSTOMER {
        string name
        string email
    }
    ORDER {
        int orderNumber
        date orderDate
    }"""
        },
        {
            "name": "Pie Chart",
            "code": """pie title Market Share
    "Product A" : 45
    "Product B" : 30
    "Product C" : 15
    "Others" : 10"""
        },
        {
            "name": "Complex Flowchart (Long)",
            "code": """flowchart TB
    subgraph Input["Input Layer"]
        A1[User Request]
        A2[System Config]
        A3[External Data]
    end
    
    subgraph Process["Processing Layer"]
        B1[Validate Input]
        B2[Transform Data]
        B3[Apply Rules]
        B4[Generate Output]
    end
    
    subgraph Output["Output Layer"]
        C1[Format Response]
        C2[Log Results]
        C3[Send Notification]
    end
    
    A1 --> B1
    A2 --> B1
    A3 --> B2
    B1 --> B2
    B2 --> B3
    B3 --> B4
    B4 --> C1
    B4 --> C2
    B4 --> C3"""
        }
    ]
    
    print("=" * 60)
    print("Mermaid Diagram Rendering Test")
    print("=" * 60)
    
    results = {"success": 0, "failed": 0}
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n[{i}/{len(test_cases)}] Testing: {test['name']}")
        print("-" * 40)
        
        img_data = generator._render_mermaid_via_kroki(test["code"])
        method_used = "Kroki.io"
        
        if not img_data:
            print("  Kroki.io failed, trying mermaid.ink...")
            img_data = generator._render_mermaid_via_ink(test["code"])
            method_used = "mermaid.ink"
        
        if img_data:
            import hashlib
            img_hash = hashlib.md5(test["code"].encode()).hexdigest()[:12]
            img_path = generator.image_cache_dir / f"test_mermaid_{img_hash}.png"
            
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
            
            img.save(str(img_path), "PNG", optimize=True)
            
            print(f"  ✅ SUCCESS via {method_used}")
            print(f"  Image size: {img.size[0]}x{img.size[1]}")
            print(f"  Saved to: {img_path}")
            results["success"] += 1
        else:
            print(f"  ❌ FAILED - All render methods failed")
            results["failed"] += 1
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"  Total tests: {len(test_cases)}")
    print(f"  Successful:  {results['success']}")
    print(f"  Failed:      {results['failed']}")
    print(f"  Success rate: {results['success']/len(test_cases)*100:.1f}%")
    
    if results["success"] > 0:
        print(f"\n  Images saved to: {generator.image_cache_dir}")
    
    return results["failed"] == 0


def test_mermaid_code_block_processing():
    """Test processing of Mermaid code blocks in content."""
    
    content = """
# Test Document

This is a test document with Mermaid diagrams.

## Architecture Overview

The system architecture is shown below:

```mermaid
flowchart LR
    Client --> API
    API --> Database
    API --> Cache
```

## Process Flow

The process flow is as follows:

```mermaid
sequenceDiagram
    User->>App: Login
    App->>Auth: Validate
    Auth-->>App: Token
    App-->>User: Success
```

## Conclusion

This concludes the test.
"""
    
    print("\n" + "=" * 60)
    print("Mermaid Code Block Processing Test")
    print("=" * 60)
    
    processed = generator._process_mermaid_code_blocks(content)
    
    mermaid_blocks_before = content.count("```mermaid")
    mermaid_blocks_after = processed.count("```mermaid")
    rendered_images = processed.count("[RENDERED_MERMAID_IMAGE:")
    
    print(f"\n  Mermaid blocks before: {mermaid_blocks_before}")
    print(f"  Mermaid blocks after:  {mermaid_blocks_after}")
    print(f"  Rendered images:       {rendered_images}")
    
    if rendered_images == mermaid_blocks_before and mermaid_blocks_after == 0:
        print("\n  ✅ All Mermaid blocks successfully processed!")
        return True
    else:
        print("\n  ❌ Some Mermaid blocks failed to process")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("MERMAID RENDERING TEST SUITE")
    print("=" * 60)
    
    test1_passed = test_mermaid_rendering()
    test2_passed = test_mermaid_code_block_processing()
    
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"  Rendering Test:        {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"  Code Block Test:       {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    print("=" * 60)
    
    sys.exit(0 if (test1_passed and test2_passed) else 1)
