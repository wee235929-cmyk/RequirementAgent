"""
Academic Report Generator - 学术报告生成器

生成出版级质量的研究报告，支持 PDF 和 Word 双格式输出。

主要功能：
    - 学术论文格式（标题、摘要、章节、参考文献）
    - 图片自动下载、缩放和标注
    - 表格解析和格式化渲染
    - Mermaid 图表渲染（如果可用）
    - 统一的排版和间距

输出格式：
    - PDF: 使用 ReportLab 生成，支持中文
    - Word: 使用 python-docx 生成，兼容 Office

使用示例：
    generator = PDFReportGenerator()
    pdf_path, docx_path = generator.generate_both(
        title="研究报告",
        content="# 报告内容...",
        images=[{"url": "...", "title": "..."}]
    )
"""
import os
import sys
import re
import io
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import REPORTS_DIR
from utils import get_logger

logger = get_logger(__name__)


class AcademicReportGenerator:
    """
    学术报告生成器
    
    生成符合学术论文规范的研究报告，支持 PDF 和 Word 双格式输出。
    
    主要特性：
        - 学术论文格式（标题、作者、日期、摘要、章节、参考文献）
        - 图片自动编号和标注（Figure 1, Figure 2...）
        - 表格自动编号和格式化（Table 1, Table 2...）
        - 统一的 Times New Roman 字体和学术排版
        - 支持 Markdown 格式的内容解析
    
    Attributes:
        output_dir: 报告输出目录
        image_cache_dir: 图片缓存目录
        FIGURE_COUNTER: 图片计数器
        TABLE_COUNTER: 表格计数器
    """
    
    # 图片和表格计数器（每个报告重置）
    FIGURE_COUNTER = 0
    TABLE_COUNTER = 0
    
    def __init__(self, output_dir: str = None):
        """
        初始化报告生成器
        
        Args:
            output_dir: 报告输出目录，默认使用 config.REPORTS_DIR
        """
        self.output_dir = Path(output_dir) if output_dir else REPORTS_DIR
        self.output_dir.mkdir(exist_ok=True)
        
        # 图片缓存目录，用于存储下载的图片
        self.image_cache_dir = self.output_dir / "image_cache"
        self.image_cache_dir.mkdir(exist_ok=True)
        
        # 已下载图片的缓存（URL -> 本地路径）
        self._downloaded_images = {}
        self._reset_counters()
        
        # 注册中文字体
        self._chinese_fonts_available = self._register_chinese_fonts()
    
    def _register_chinese_fonts(self) -> bool:
        """
        注册中文字体（SimSun宋体、SimHei黑体、SimKai楷体、SimFang仿宋）。
        从 Windows 系统字体目录加载 TTF/TTC 字体文件。
        
        Returns:
            True if at least one Chinese font was registered successfully
        """
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            
            fonts_dir = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')
            
            font_map = {
                'SimSun': ['simsun.ttc', 'simsun.ttf', 'SIMSUN.TTC', 'SIMSUN.TTF'],
                'SimHei': ['simhei.ttf', 'SIMHEI.TTF', 'msyh.ttc', 'msyh.ttf'],
                'SimKai': ['simkai.ttf', 'SIMKAI.TTF'],
                'SimFang': ['simfang.ttf', 'SIMFANG.TTF'],
            }
            
            registered = []
            for font_name, candidates in font_map.items():
                for candidate in candidates:
                    font_path = os.path.join(fonts_dir, candidate)
                    if os.path.exists(font_path):
                        try:
                            pdfmetrics.registerFont(TTFont(font_name, font_path))
                            registered.append(font_name)
                            logger.info(f"Registered Chinese font: {font_name} from {candidate}")
                            break
                        except Exception as fe:
                            logger.debug(f"Failed to register {font_name} from {candidate}: {fe}")
            
            # 注册粗体/斜体变体（使用相同字体文件）
            if 'SimHei' in registered:
                try:
                    from reportlab.pdfbase.pdfmetrics import registerFontFamily
                    registerFontFamily('SimSun', normal='SimSun', bold='SimHei', italic='SimKai', boldItalic='SimHei')
                except Exception:
                    pass
            
            if registered:
                logger.info(f"Chinese fonts registered: {registered}")
                return True
            else:
                logger.warning("No Chinese fonts found. Chinese text in PDF may not render correctly.")
                # 尝试 CID 字体作为后备
                try:
                    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
                    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
                    logger.info("Registered CID font STSong-Light as fallback")
                    return True
                except Exception:
                    pass
                return False
                
        except ImportError:
            logger.warning("reportlab not available, skipping Chinese font registration")
            return False
        except Exception as e:
            logger.warning(f"Failed to register Chinese fonts: {e}")
            return False
    
    def _is_chinese_content(self, text: str) -> bool:
        """检测文本是否包含中文字符。"""
        if not text:
            return False
        chinese_chars = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
        return chinese_chars > len(text) * 0.05 or chinese_chars > 10
    
    def _reset_counters(self):
        """重置图片和表格计数器（每个新报告调用）"""
        self.FIGURE_COUNTER = 0
        self.TABLE_COUNTER = 0
    
    def _next_figure_num(self) -> int:
        """获取下一个图片编号"""
        self.FIGURE_COUNTER += 1
        return self.FIGURE_COUNTER
    
    def _next_table_num(self) -> int:
        """获取下一个表格编号"""
        self.TABLE_COUNTER += 1
        return self.TABLE_COUNTER
    
    def _download_image(self, url: str, timeout: int = 10) -> Optional[str]:
        """Download an image from URL and cache it locally."""
        if url in self._downloaded_images:
            return self._downloaded_images[url]
        
        try:
            import requests
            from PIL import Image
            
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, timeout=timeout, stream=True, headers=headers)
            response.raise_for_status()
            
            img = Image.open(io.BytesIO(response.content))
            
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            max_width = 1200
            max_height = 900
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            img_path = self.image_cache_dir / f"img_{url_hash}.png"
            img.save(str(img_path), "PNG", optimize=True)
            
            self._downloaded_images[url] = str(img_path)
            logger.info(f"Downloaded image: {url[:50]}...")
            return str(img_path)
            
        except Exception as e:
            logger.warning(f"Failed to download image {url[:50]}...: {e}")
            return None
    
    def _parse_table_from_text(self, table_text: str) -> Optional[List[List[str]]]:
        """Parse a markdown-style table into a 2D list."""
        try:
            lines = [l.strip() for l in table_text.strip().split('\n') if l.strip()]
            if len(lines) < 2:
                return None
            
            table_data = []
            for line in lines:
                if line.startswith('|') and line.endswith('|'):
                    cells = [c.strip() for c in line[1:-1].split('|')]
                    if all(set(c) <= {'-', ':', ' '} for c in cells):
                        continue
                    table_data.append(cells)
            
            return table_data if len(table_data) >= 2 else None
            
        except Exception as e:
            logger.warning(f"Failed to parse table: {e}")
            return None
    
    def _create_table_with_caption(self, data: List[List[str]], source: str = "", 
                                    title: str = "", is_chinese: bool = False) -> List[Any]:
        """
        Create a table with proper academic formatting and source attribution.
        Table number and source appear ABOVE the table.
        For Chinese: uses 三线表 style with Chinese fonts.
        """
        from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.lib.enums import TA_CENTER
        
        flowables = []
        styles = getSampleStyleSheet()
        
        font_body = 'SimSun' if (is_chinese and self._chinese_fonts_available) else 'Times-Roman'
        font_caption = 'SimHei' if (is_chinese and self._chinese_fonts_available) else 'Times-Bold'
        
        table_num = self._next_table_num()
        if is_chinese:
            caption_text = f"<b>表{table_num}</b>"
            if title:
                caption_text += f" {title}"
        else:
            caption_text = f"<b>Table {table_num}.</b> {title}" if title else f"<b>Table {table_num}.</b>"
            if source:
                caption_text += f" <i>(Source: {source})</i>"
        
        caption_style = ParagraphStyle(
            'TableCaption',
            parent=styles['Normal'],
            fontSize=9,
            alignment=TA_CENTER,
            spaceBefore=8,
            spaceAfter=4,
            textColor=colors.HexColor('#333333'),
            fontName=font_caption
        )
        caption_text = caption_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        caption_text = caption_text.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
        caption_text = caption_text.replace('&lt;i&gt;', '<i>').replace('&lt;/i&gt;', '</i>')
        flowables.append(Paragraph(caption_text, caption_style))
        
        col_count = max(len(row) for row in data)
        for row in data:
            while len(row) < col_count:
                row.append("")
        
        wrapped_data = []
        for row_idx, row in enumerate(data):
            wrapped_row = []
            for cell in row:
                cell_font = font_caption if row_idx == 0 else font_body
                cell_style = ParagraphStyle(
                    'CellStyle',
                    parent=styles['Normal'],
                    fontSize=8,
                    leading=10,
                    wordWrap='CJK',
                    fontName=cell_font
                )
                cell_text = str(cell)
                cell_text = re.sub(r'^\*+|\*+$', '', cell_text)
                cell_text = re.sub(r'\*\*(.+?)\*\*', r'\1', cell_text)
                cell_text = re.sub(r'\*(.+?)\*', r'\1', cell_text)
                cell_text = cell_text.strip()
                cell_text = cell_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                if row_idx == 0:
                    cell_text = f"<b>{cell_text}</b>"
                wrapped_row.append(Paragraph(cell_text, cell_style))
            wrapped_data.append(wrapped_row)
        
        available_width = 6.2 * inch
        if col_count <= 2:
            col_widths = [available_width / col_count] * col_count
        elif col_count <= 4:
            col_widths = [available_width / col_count] * col_count
        else:
            first_col_width = available_width * 0.25
            other_width = (available_width - first_col_width) / (col_count - 1)
            col_widths = [first_col_width] + [other_width] * (col_count - 1)
        
        table = Table(wrapped_data, colWidths=col_widths, repeatRows=1)
        
        if is_chinese:
            # 三线表样式
            table_style = TableStyle([
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LINEABOVE', (0, 0), (-1, 0), 1.5, colors.black),       # 顶线
                ('LINEBELOW', (0, 0), (-1, 0), 0.75, colors.black),      # 表头下线
                ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.black),     # 底线
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ])
        else:
            table_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ])
            for i in range(1, len(wrapped_data)):
                bg_color = colors.HexColor('#f8f9fa') if i % 2 == 0 else colors.white
                table_style.add('BACKGROUND', (0, i), (-1, i), bg_color)
        
        table.setStyle(table_style)
        flowables.append(table)
        flowables.append(Spacer(1, 8))
        
        return flowables
    
    def _create_figure_with_caption(self, img_path: str, title: str = "", 
                                      source: str = "", is_chinese: bool = False) -> List[Any]:
        """
        Create a figure with academic-style caption below the image.
        Format: Figure X. Title (Source: source) / 图X Title
        """
        from reportlab.platypus import Image, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        
        flowables = []
        font_caption = 'SimHei' if (is_chinese and self._chinese_fonts_available) else 'Times-Roman'
        
        try:
            img = Image(img_path)
            
            max_width = 5.0 * inch
            max_height = 3.5 * inch
            
            aspect = img.imageWidth / img.imageHeight
            if img.imageWidth > max_width:
                img.drawWidth = max_width
                img.drawHeight = max_width / aspect
            if img.drawHeight > max_height:
                img.drawHeight = max_height
                img.drawWidth = max_height * aspect
            
            img.hAlign = 'CENTER'
            flowables.append(Spacer(1, 6))
            flowables.append(img)
            
            styles = getSampleStyleSheet()
            fig_num = self._next_figure_num()
            
            if is_chinese:
                caption_text = f"<b>图{fig_num}</b>"
                if title:
                    caption_text += f" {title}"
                if source and source != 'Unknown':
                    caption_text += f"（来源：{source}）"
            else:
                caption_text = f"<b>Figure {fig_num}.</b>"
                if title:
                    caption_text += f" {title}"
                if source:
                    caption_text += f" <i>(Source: {source})</i>"
            
            caption_style = ParagraphStyle(
                'FigureCaption',
                parent=styles['Normal'],
                fontSize=9,
                alignment=TA_CENTER,
                textColor=colors.HexColor('#333333'),
                spaceBefore=4,
                spaceAfter=8,
                fontName=font_caption
            )
            caption_text = caption_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            caption_text = caption_text.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
            caption_text = caption_text.replace('&lt;i&gt;', '<i>').replace('&lt;/i&gt;', '</i>')
            flowables.append(Paragraph(caption_text, caption_style))
            
        except Exception as e:
            logger.warning(f"Failed to create figure flowable: {e}")
        
        return flowables
    
    def _get_academic_styles(self, is_chinese: bool = False):
        """
        Get academic paper styles for PDF generation.
        
        Args:
            is_chinese: If True, use Chinese academic paper fonts and formatting
        """
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
        from reportlab.lib.colors import HexColor, black
        
        styles = getSampleStyleSheet()
        
        if is_chinese and self._chinese_fonts_available:
            # 中文学术论文格式
            # 二号黑体=22pt, 三号=16pt, 四号=14pt, 小四=12pt, 五号=10.5pt, 小五=9pt
            font_body = 'SimSun'       # 宋体 - 正文
            font_heading = 'SimHei'    # 黑体 - 标题
            font_kai = 'SimKai' if self._chinese_fonts_available else 'SimSun'  # 楷体 - 作者
            font_fang = 'SimFang' if self._chinese_fonts_available else 'SimSun'  # 仿宋
            
            custom_styles = {
                'title': ParagraphStyle(
                    'AcademicTitle',
                    parent=styles['Heading1'],
                    fontSize=22,        # 二号
                    leading=28,
                    spaceAfter=8,
                    alignment=TA_CENTER,
                    textColor=black,
                    fontName=font_heading
                ),
                'author': ParagraphStyle(
                    'Author',
                    parent=styles['Normal'],
                    fontSize=14,        # 四号楷体
                    leading=18,
                    alignment=TA_CENTER,
                    spaceAfter=4,
                    fontName=font_kai
                ),
                'date': ParagraphStyle(
                    'Date',
                    parent=styles['Normal'],
                    fontSize=12,        # 小四
                    leading=16,
                    alignment=TA_CENTER,
                    spaceAfter=16,
                    fontName=font_body
                ),
                'abstract_title': ParagraphStyle(
                    'AbstractTitle',
                    parent=styles['Heading2'],
                    fontSize=9,         # 小五号黑体
                    leading=13,
                    spaceBefore=12,
                    spaceAfter=6,
                    alignment=TA_LEFT,
                    firstLineIndent=24,
                    fontName=font_heading
                ),
                'abstract': ParagraphStyle(
                    'Abstract',
                    parent=styles['Normal'],
                    fontSize=9,         # 小五号
                    leading=13,
                    alignment=TA_JUSTIFY,
                    leftIndent=24,
                    rightIndent=24,
                    firstLineIndent=18,
                    spaceAfter=16,
                    fontName=font_body
                ),
                'keywords': ParagraphStyle(
                    'Keywords',
                    parent=styles['Normal'],
                    fontSize=9,         # 小五号黑体
                    leading=13,
                    alignment=TA_LEFT,
                    firstLineIndent=24,
                    spaceAfter=12,
                    fontName=font_heading
                ),
                'h1': ParagraphStyle(
                    'SectionH1',
                    parent=styles['Heading1'],
                    fontSize=14,        # 四号宋体加粗
                    leading=22,
                    spaceBefore=16,
                    spaceAfter=8,
                    textColor=black,
                    fontName=font_heading
                ),
                'h2': ParagraphStyle(
                    'SectionH2',
                    parent=styles['Heading2'],
                    fontSize=12,        # 小四号宋体加粗
                    leading=20,
                    spaceBefore=12,
                    spaceAfter=6,
                    textColor=black,
                    fontName=font_heading
                ),
                'h3': ParagraphStyle(
                    'SectionH3',
                    parent=styles['Heading3'],
                    fontSize=12,        # 小四号宋体加粗
                    leading=20,
                    spaceBefore=10,
                    spaceAfter=4,
                    textColor=black,
                    fontName=font_heading
                ),
                'h4': ParagraphStyle(
                    'SectionH4',
                    parent=styles['Heading3'],
                    fontSize=12,        # 小四号宋体加粗
                    leading=20,
                    spaceBefore=8,
                    spaceAfter=4,
                    textColor=black,
                    fontName=font_heading
                ),
                'body': ParagraphStyle(
                    'BodyText',
                    parent=styles['Normal'],
                    fontSize=12,        # 小四号宋体
                    leading=22,         # 1.5倍行距
                    alignment=TA_JUSTIFY,
                    spaceAfter=0,
                    firstLineIndent=24, # 两字符缩进
                    fontName=font_body
                ),
                'body_first': ParagraphStyle(
                    'BodyTextFirst',
                    parent=styles['Normal'],
                    fontSize=12,
                    leading=22,
                    alignment=TA_JUSTIFY,
                    spaceAfter=0,
                    firstLineIndent=24,
                    fontName=font_body
                ),
                'bullet': ParagraphStyle(
                    'BulletPoint',
                    parent=styles['Normal'],
                    fontSize=12,
                    leading=22,
                    leftIndent=24,
                    spaceAfter=0,
                    fontName=font_body
                ),
                'numbered': ParagraphStyle(
                    'NumberedItem',
                    parent=styles['Normal'],
                    fontSize=12,
                    leading=22,
                    leftIndent=24,
                    spaceAfter=0,
                    fontName=font_body
                ),
                'reference': ParagraphStyle(
                    'Reference',
                    parent=styles['Normal'],
                    fontSize=10.5,      # 五号宋体
                    leading=16,
                    leftIndent=18,
                    firstLineIndent=-18,
                    spaceAfter=3,
                    fontName=font_body
                ),
                'conclusion': ParagraphStyle(
                    'Conclusion',
                    parent=styles['Normal'],
                    fontSize=10.5,      # 五号宋体加粗
                    leading=16,
                    alignment=TA_JUSTIFY,
                    spaceAfter=4,
                    firstLineIndent=0,
                    fontName=font_heading
                ),
            }
        else:
            # English academic paper format
            custom_styles = {
                'title': ParagraphStyle(
                    'AcademicTitle',
                    parent=styles['Heading1'],
                    fontSize=16,
                    leading=20,
                    spaceAfter=6,
                    alignment=TA_CENTER,
                    textColor=black,
                    fontName='Times-Bold'
                ),
                'author': ParagraphStyle(
                    'Author',
                    parent=styles['Normal'],
                    fontSize=11,
                    alignment=TA_CENTER,
                    spaceAfter=4,
                    fontName='Times-Roman'
                ),
                'date': ParagraphStyle(
                    'Date',
                    parent=styles['Normal'],
                    fontSize=10,
                    alignment=TA_CENTER,
                    spaceAfter=16,
                    fontName='Times-Italic'
                ),
                'abstract_title': ParagraphStyle(
                    'AbstractTitle',
                    parent=styles['Heading2'],
                    fontSize=11,
                    spaceBefore=12,
                    spaceAfter=6,
                    alignment=TA_CENTER,
                    fontName='Times-Bold'
                ),
                'abstract': ParagraphStyle(
                    'Abstract',
                    parent=styles['Normal'],
                    fontSize=10,
                    leading=13,
                    alignment=TA_JUSTIFY,
                    leftIndent=36,
                    rightIndent=36,
                    spaceAfter=16,
                    fontName='Times-Italic'
                ),
                'h1': ParagraphStyle(
                    'SectionH1',
                    parent=styles['Heading1'],
                    fontSize=14,
                    leading=17,
                    spaceBefore=16,
                    spaceAfter=8,
                    textColor=black,
                    fontName='Times-Bold'
                ),
                'h2': ParagraphStyle(
                    'SectionH2',
                    parent=styles['Heading2'],
                    fontSize=12,
                    leading=15,
                    spaceBefore=12,
                    spaceAfter=6,
                    textColor=black,
                    fontName='Times-Bold'
                ),
                'h3': ParagraphStyle(
                    'SectionH3',
                    parent=styles['Heading3'],
                    fontSize=11,
                    leading=14,
                    spaceBefore=10,
                    spaceAfter=4,
                    textColor=black,
                    fontName='Times-Bold'
                ),
                'body': ParagraphStyle(
                    'BodyText',
                    parent=styles['Normal'],
                    fontSize=10,
                    leading=13,
                    alignment=TA_JUSTIFY,
                    spaceAfter=6,
                    firstLineIndent=18,
                    fontName='Times-Roman'
                ),
                'body_first': ParagraphStyle(
                    'BodyTextFirst',
                    parent=styles['Normal'],
                    fontSize=10,
                    leading=13,
                    alignment=TA_JUSTIFY,
                    spaceAfter=6,
                    firstLineIndent=0,
                    fontName='Times-Roman'
                ),
                'bullet': ParagraphStyle(
                    'BulletPoint',
                    parent=styles['Normal'],
                    fontSize=10,
                    leading=13,
                    leftIndent=24,
                    spaceAfter=3,
                    fontName='Times-Roman'
                ),
                'numbered': ParagraphStyle(
                    'NumberedItem',
                    parent=styles['Normal'],
                    fontSize=10,
                    leading=13,
                    leftIndent=24,
                    spaceAfter=3,
                    fontName='Times-Roman'
                ),
                'reference': ParagraphStyle(
                    'Reference',
                    parent=styles['Normal'],
                    fontSize=9,
                    leading=11,
                    leftIndent=18,
                    firstLineIndent=-18,
                    spaceAfter=4,
                    fontName='Times-Roman'
                ),
            }
        
        return styles, custom_styles
    
    def _prepare_images(self, images: List[Dict], max_images: int = 12) -> List[Dict]:
        """Download and prepare images for embedding."""
        downloaded = []
        for img_info in images[:max_images]:
            url = img_info.get("url") or img_info.get("thumbnail")
            if url:
                local_path = self._download_image(url)
                if local_path:
                    downloaded.append({
                        "path": local_path,
                        "title": img_info.get("title", ""),
                        "category": img_info.get("category", ""),
                        "source": img_info.get("source", "Unknown")
                    })
        logger.info(f"Prepared {len(downloaded)} images for report")
        return downloaded
    
    def _distribute_images_to_sections(self, images: List[Dict], sections: List[str]) -> Dict[str, List[Dict]]:
        """Distribute images evenly across major sections."""
        distribution = {}
        if not images or not sections:
            return distribution
        
        images_per_section = max(1, len(images) // len(sections))
        img_idx = 0
        
        for section in sections:
            section_images = []
            for _ in range(images_per_section):
                if img_idx < len(images):
                    section_images.append(images[img_idx])
                    img_idx += 1
            if section_images:
                distribution[section.lower()] = section_images
        
        return distribution
    
    def _render_mermaid_to_image(self, mermaid_type: str, description: str, context: str = "") -> Optional[str]:
        """
        Generate a Mermaid diagram and render it to an image file.
        
        Args:
            mermaid_type: Type of diagram (flowchart, sequence, class, pie, gantt, etc.)
            description: Description of what the diagram should show
            context: Additional context from the report content
            
        Returns:
            Path to the generated image file, or None if failed
        """
        try:
            from tools.chart import MermaidChartTool
            import base64
            import requests
            
            chart_tool = MermaidChartTool()
            
            type_mapping = {
                'flowchart': 'flowchart',
                'sequence': 'sequence',
                'class': 'class',
                'state': 'flowchart',
                'er': 'er',
                'gantt': 'flowchart',
                'pie': 'flowchart',
            }
            diagram_type = type_mapping.get(mermaid_type.lower(), 'flowchart')
            
            prompt = f"{description}\n\nContext: {context[:500]}" if context else description
            mermaid_code = chart_tool.generate(prompt, diagram_type)
            
            code_match = re.search(r'```mermaid\s*([\s\S]*?)\s*```', mermaid_code)
            if code_match:
                clean_code = code_match.group(1).strip()
            else:
                clean_code = mermaid_code.strip()
            
            img_data = self._try_render_with_fix(clean_code)
            
            if not img_data:
                logger.warning(f"All Mermaid render methods failed for: {description[:30]}...")
                return None
            
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(img_data))
                
                if img.mode in ('RGBA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'RGBA':
                        background.paste(img, mask=img.split()[3])
                    else:
                        background.paste(img)
                    img = background
                
                target_width = 2400
                target_height = 1680
                
                orig_width, orig_height = img.size
                ratio = min(target_width / orig_width, target_height / orig_height)
                if ratio < 1:
                    new_size = (int(orig_width * ratio), int(orig_height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                elif ratio > 1 and orig_width < 800:
                    # 小图放大以提高清晰度
                    scale = min(ratio, 2.0)
                    new_size = (int(orig_width * scale), int(orig_height * scale))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                img_hash = hashlib.md5(clean_code.encode()).hexdigest()[:12]
                img_path = self.image_cache_dir / f"mermaid_{img_hash}.png"
                img.save(str(img_path), "PNG", optimize=True)
                
                logger.info(f"Generated Mermaid diagram: {mermaid_type} - {description[:30]}...")
                return str(img_path)
                
            except Exception as render_e:
                logger.warning(f"Failed to process Mermaid image: {render_e}")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to generate Mermaid diagram: {e}")
            return None
    
    def _parse_mermaid_marker(self, line: str) -> Optional[Tuple[str, str]]:
        """
        Parse a [MERMAID: type | description] marker.
        
        Returns:
            Tuple of (type, description) or None if not a valid marker
        """
        match = re.match(r'\[MERMAID:\s*(\w+)\s*\|\s*(.+?)\]', line, re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return None
    
    def _fix_mermaid_syntax(self, mermaid_code: str) -> str:
        """
        Fix common Mermaid syntax errors generated by LLMs.
        
        Handles:
            - Chinese characters in labels (cause rendering failures on Kroki/mermaid.ink)
            - <br> -> <br/> conversion
            - graph -> flowchart conversion
            - Invalid arrow syntax (-> to -->)
            - Special characters in node labels
            - Quotes inside edge labels
            - Multi-line node labels
            - Stray HTML tags and Markdown formatting
        """
        fixed = mermaid_code.strip()
        
        # 移除可能被LLM误加的 ``` 标记
        fixed = re.sub(r'^```\s*mermaid\s*\n?', '', fixed)
        fixed = re.sub(r'\n?```\s*$', '', fixed)
        
        # 修复 <br> -> <br/>
        fixed = re.sub(r'<br\s*/?>', '<br/>', fixed)
        
        # 将 graph TD/LR 转换为 flowchart TD/LR
        fixed = re.sub(r'^graph\s+(TD|LR|TB|BT|RL)', r'flowchart \1', fixed)
        
        # 修复无效箭头语法：-> 改为 -->（仅在 flowchart 中）
        if fixed.startswith('flowchart'):
            fixed = re.sub(r'(\w)\s*->\s*(\w)', r'\1 --> \2', fixed)
            fixed = re.sub(r'(\])\s*->\s*(\w)', r'\1 --> \2', fixed)
            fixed = re.sub(r'(\))\s*->\s*(\w)', r'\1 --> \2', fixed)
        
        # 修复多行节点标签
        fixed = re.sub(r'\[\s*\n\s*', '[', fixed)
        fixed = re.sub(r'\s*\n\s*\]', ']', fixed)
        
        # 修复边标签中的引号
        fixed = re.sub(r'-->\s*\|([^|]*["\'][^|]*)\|', 
                       lambda m: f'-->|{m.group(1).replace(chr(34), "").replace(chr(39), "")}|', fixed)
        
        # 标准化箭头格式
        fixed = re.sub(r'(\w)\s*-+>\s*\|([^|]*)\|\s*(\w)', r'\1 -->|\2| \3', fixed)
        
        # 移除节点标签中的特殊字符
        def clean_node_label(match):
            prefix = match.group(1)
            label = match.group(2)
            suffix = match.group(3)
            label = label.replace('"', '').replace("'", "")
            label = label.replace('(', '').replace(')', '')
            label = label.replace('{', '').replace('}', '')
            label = label.replace('#', '').replace('&', 'and')
            label = label.replace(';', ' ').replace('%', ' percent')
            if len(label) > 45:
                label = label[:42] + '...'
            return f'{prefix}{label}{suffix}'
        
        fixed = re.sub(r'(\[)([^\]]+)(\])', clean_node_label, fixed)
        
        # 移除 Markdown 格式标记
        fixed = re.sub(r'\*\*([^*]+)\*\*', r'\1', fixed)
        fixed = re.sub(r'\*([^*]+)\*', r'\1', fixed)
        
        # 移除除 <br/> 以外的 HTML 标签
        fixed = re.sub(r'<(?!br/)([^>]+)>', '', fixed)
        
        # 清理空行
        lines = fixed.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.rstrip()
            if line.strip():
                cleaned_lines.append(line)
            elif cleaned_lines and cleaned_lines[-1].strip():
                cleaned_lines.append('')
        fixed = '\n'.join(cleaned_lines)
        
        # 修复 flowchart 中跨行的花括号
        if fixed.startswith('flowchart '):
            fixed = re.sub(r'\{([^}]*)\n([^}]*)\}', 
                          lambda m: '{' + m.group(1).replace('\n', ' ') + m.group(2) + '}', fixed)
        
        # 关键修复：移除中文字符（Kroki/mermaid.ink 无法渲染中文）
        # 对于 quadrantChart, pie 等使用引号包裹标签的图表类型，替换中文为拼音/英文
        if any(ord(ch) > 0x4e00 for ch in fixed):
            # 替换引号内的中文文本
            def replace_chinese_in_quotes(match):
                quote = match.group(1)
                text = match.group(2)
                # 如果包含中文，尝试保留英文部分
                if any('\u4e00' <= ch <= '\u9fff' for ch in text):
                    # 提取英文部分
                    english_parts = re.findall(r'[a-zA-Z0-9\s\-_.]+', text)
                    if english_parts:
                        return f'{quote}{"".join(english_parts).strip()}{quote}'
                    else:
                        return f'{quote}Item{quote}'
                return match.group(0)
            
            fixed = re.sub(r'(["\u201c])([^"\u201d]*[\u4e00-\u9fff][^"\u201d]*)(["\u201d])', 
                          lambda m: replace_chinese_in_quotes(m) if m.group(1) in ('"', '\u201c') else m.group(0), 
                          fixed)
            # 替换中文引号为英文引号
            fixed = fixed.replace('\u201c', '"').replace('\u201d', '"')
            
            # 对于轴标签等非引号包裹的中文
            lines = fixed.split('\n')
            new_lines = []
            for line in lines:
                # 保留第一行（图表类型声明）
                if line.strip() and not any('\u4e00' <= ch <= '\u9fff' for ch in line):
                    new_lines.append(line)
                elif line.strip():
                    # 移除中文字符，保留英文和标点
                    cleaned = re.sub(r'[\u4e00-\u9fff\u201c\u201d\u2018\u2019\u3001\u3002\uff0c\uff1a\uff1b]+', '', line)
                    if cleaned.strip() and not cleaned.strip().startswith('--'):
                        new_lines.append(cleaned)
                    elif not cleaned.strip():
                        # 整行都是中文，跳过
                        continue
                    else:
                        new_lines.append(cleaned)
                else:
                    new_lines.append(line)
            fixed = '\n'.join(new_lines)
        
        return fixed
    
    def _aggressive_simplify_mermaid(self, mermaid_code: str) -> str:
        """
        Aggressively simplify Mermaid code as last resort.
        Strips all styling, shortens labels, removes subgraphs.
        """
        simplified = mermaid_code
        
        # 移除所有 style/linkStyle/classDef 行
        simplified = re.sub(r'^\s*(style|linkStyle|classDef|class)\s+[^\n]+\n?', '', simplified, flags=re.MULTILINE)
        
        # 移除 subgraph 结构（保留内容）
        simplified = re.sub(r'^\s*subgraph\s+[^\n]*\n?', '', simplified, flags=re.MULTILINE)
        simplified = re.sub(r'^\s*end\s*$', '', simplified, flags=re.MULTILINE)
        
        # 截断所有节点标签到 25 个字符
        simplified = re.sub(r'\[([^\]]{25,})\]', lambda m: f'[{m.group(1)[:22]}...]', simplified)
        
        # 移除所有 ::: 类引用
        simplified = re.sub(r':::[\w-]+', '', simplified)
        
        # 移除空行
        lines = [l for l in simplified.split('\n') if l.strip()]
        simplified = '\n'.join(lines)
        
        return simplified.strip()
    
    def _try_render_with_fix(self, mermaid_code: str, max_attempts: int = 3) -> Optional[bytes]:
        """
        Try to render Mermaid code with progressive fix strategy.
        
        Strategy:
            1. Pre-fix: Always apply syntax fixes before first attempt
            2. Attempt 1: Render pre-fixed code
            3. Attempt 2: Simplify complex elements and retry
            4. Attempt 3: Aggressive simplification (strip styles, shorten labels)
        """
        # 预处理：始终先修复常见语法错误（减少不必要的渲染失败）
        current_code = self._fix_mermaid_syntax(mermaid_code)
        
        # 预验证：检查基本结构是否合理
        first_line = current_code.split('\n')[0].strip().lower() if current_code.strip() else ''
        valid_starts = ['flowchart', 'sequencediagram', 'classdiagram', 'statediagram',
                       'erdiagram', 'gantt', 'pie', 'mindmap', 'timeline', 'quadrantchart',
                       'gitgraph', 'graph', 'c4context', 'journey', 'requirementdiagram']
        if not any(first_line.startswith(s) for s in valid_starts):
            logger.warning(f"Mermaid code has invalid start: '{first_line[:30]}...'")
            if '-->' in current_code or '---' in current_code:
                current_code = 'flowchart TD\n' + current_code
                logger.info("Added 'flowchart TD' header to Mermaid code")
        
        for attempt in range(max_attempts):
            img_data = self._render_mermaid_via_kroki(current_code)
            if img_data:
                if attempt > 0:
                    logger.info(f"Mermaid rendered successfully after {attempt} fix attempt(s)")
                return img_data
            
            img_data = self._render_mermaid_via_ink(current_code)
            if img_data:
                if attempt > 0:
                    logger.info(f"Mermaid rendered via ink after {attempt} fix attempt(s)")
                return img_data
            
            if attempt < max_attempts - 1:
                logger.info(f"Mermaid render failed, attempting deeper fix (attempt {attempt + 1})")
                if attempt == 0:
                    current_code = self._simplify_mermaid(current_code)
                elif attempt == 1:
                    current_code = self._aggressive_simplify_mermaid(current_code)
        
        return None
    
    def _simplify_mermaid(self, mermaid_code: str) -> str:
        """Simplify complex Mermaid code that may cause rendering issues."""
        simplified = mermaid_code
        
        simplified = re.sub(r'\[([^\]]{80,})\]', lambda m: f'[{m.group(1)[:75]}...]', simplified)
        
        simplified = re.sub(r'style\s+\w+\s+[^\n]+\n?', '', simplified)
        simplified = re.sub(r'linkStyle\s+[^\n]+\n?', '', simplified)
        
        simplified = re.sub(r':::[\w-]+', '', simplified)
        
        return simplified.strip()
    
    def _render_mermaid_via_kroki(self, mermaid_code: str) -> Optional[bytes]:
        """Render Mermaid code using Kroki.io API (supports longer code via POST)."""
        import zlib
        import base64
        import requests
        
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
            logger.warning(f"Kroki render failed: {e}")
            return None
    
    def _render_mermaid_via_ink(self, mermaid_code: str) -> Optional[bytes]:
        """Render Mermaid code using mermaid.ink API."""
        import base64
        import requests
        
        try:
            encoded = base64.urlsafe_b64encode(mermaid_code.encode('utf-8')).decode('utf-8')
            mermaid_url = f"https://mermaid.ink/img/{encoded}?scale=5"
            
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(mermaid_url, timeout=30, headers=headers)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.warning(f"mermaid.ink render failed: {e}")
            return None
    
    def _process_mermaid_code_blocks(self, content: str) -> str:
        """
        Find and render all ```mermaid code blocks in the content,
        replacing them with image references. Includes automatic syntax fixing.
        """
        mermaid_pattern = re.compile(r'```mermaid\s*([\s\S]*?)\s*```', re.IGNORECASE)
        
        def render_mermaid_block(match):
            mermaid_code = match.group(1).strip()
            if not mermaid_code:
                return ""
            
            try:
                img_data = self._try_render_with_fix(mermaid_code)
                
                if not img_data:
                    logger.warning("All Mermaid render methods failed after fix attempts")
                    return ""
                
                from PIL import Image
                img = Image.open(io.BytesIO(img_data))
                
                if img.mode in ('RGBA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'RGBA':
                        background.paste(img, mask=img.split()[3])
                    else:
                        background.paste(img)
                    img = background
                
                img_hash = hashlib.md5(mermaid_code.encode()).hexdigest()[:12]
                img_path = self.image_cache_dir / f"mermaid_block_{img_hash}.png"
                img.save(str(img_path), "PNG", optimize=True)
                
                first_line = mermaid_code.split('\n')[0].strip()
                diagram_type = "Diagram"
                if first_line.startswith('flowchart') or first_line.startswith('graph'):
                    diagram_type = "Flowchart"
                elif first_line.startswith('sequenceDiagram'):
                    diagram_type = "Sequence Diagram"
                elif first_line.startswith('classDiagram'):
                    diagram_type = "Class Diagram"
                elif first_line.startswith('stateDiagram'):
                    diagram_type = "State Diagram"
                elif first_line.startswith('erDiagram'):
                    diagram_type = "ER Diagram"
                elif first_line.startswith('gantt'):
                    diagram_type = "Gantt Chart"
                elif first_line.startswith('pie'):
                    diagram_type = "Pie Chart"
                elif first_line.startswith('mindmap'):
                    diagram_type = "Mind Map"
                elif first_line.startswith('timeline'):
                    diagram_type = "Timeline"
                elif first_line.startswith('quadrantChart'):
                    diagram_type = "Quadrant Chart"
                elif first_line.startswith('gitGraph'):
                    diagram_type = "Git Graph"
                
                logger.info(f"Successfully rendered Mermaid {diagram_type}: {img_path}")
                return f"\n[RENDERED_MERMAID_IMAGE:{img_path}|{diagram_type}]\n"
                
            except Exception as e:
                logger.warning(f"Failed to render mermaid code block: {e}")
                return ""
        
        return mermaid_pattern.sub(render_mermaid_block, content)
    
    def generate(self, title: str, content: str, filename: str = None,
                 images: List[Dict] = None, tables: List[Dict] = None) -> str:
        """Generate PDF report with academic formatting."""
        return self._generate_pdf(title, content, filename, images, tables)
    
    def generate_both(self, title: str, content: str, filename: str = None,
                      images: List[Dict] = None, tables: List[Dict] = None) -> Tuple[str, str]:
        """
        Generate both PDF and Word versions of the report.
        
        Returns:
            Tuple of (pdf_path, docx_path)
        """
        self._reset_counters()
        pdf_path = self._generate_pdf(title, content, filename, images, tables)
        
        self._reset_counters()
        base_name = Path(pdf_path).stem
        docx_path = self._generate_word(title, content, base_name, images, tables)
        
        return pdf_path, docx_path
    
    def _generate_pdf(self, title: str, content: str, filename: str = None,
                      images: List[Dict] = None, tables: List[Dict] = None) -> str:
        """Generate PDF with academic paper formatting."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
            from reportlab.lib.units import inch, cm
        except ImportError:
            raise ImportError("reportlab library required for PDF generation")
        
        self._reset_counters()
        images = images or []
        tables = tables or []
        
        # 检测是否为中文内容
        is_chinese = self._is_chinese_content(title) or self._is_chinese_content(content[:500])
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"research_report_{timestamp}.pdf"
        if not filename.endswith(".pdf"):
            filename += ".pdf"
        
        pdf_path = self.output_dir / filename
        
        if is_chinese:
            # 中文论文页面设置：A4纸，左右2.6cm，上下3cm
            doc = SimpleDocTemplate(
                str(pdf_path),
                pagesize=A4,
                rightMargin=2.6*cm,
                leftMargin=2.6*cm,
                topMargin=3*cm,
                bottomMargin=3*cm
            )
        else:
            doc = SimpleDocTemplate(
                str(pdf_path),
                pagesize=A4,
                rightMargin=1*inch,
                leftMargin=1*inch,
                topMargin=0.75*inch,
                bottomMargin=0.75*inch
            )
        
        base_styles, custom = self._get_academic_styles(is_chinese=is_chinese)
        
        downloaded_images = self._prepare_images(images)
        
        major_sections = []
        for line in content.split('\n'):
            if line.strip().startswith('# '):
                major_sections.append(line.strip()[2:])
        image_distribution = self._distribute_images_to_sections(downloaded_images, major_sections)
        
        story = []
        
        story.append(Paragraph(title, custom['title']))
        if is_chinese:
            story.append(Paragraph("RAAA 深度研究系统自动生成", custom['author']))
            date_str = datetime.now().strftime("%Y年%m月%d日")
        else:
            story.append(Paragraph("Generated by RAAA Deep Research", custom['author']))
            date_str = datetime.now().strftime("%B %d, %Y")
        story.append(Paragraph(date_str, custom['date']))
        story.append(Spacer(1, 12))
        
        content = self._process_mermaid_code_blocks(content)
        
        lines = content.split('\n')
        current_section = ""
        section_image_idx = {}
        in_table = False
        table_lines = []
        after_heading = False
        in_references = False
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            if not line_stripped:
                if in_table and table_lines:
                    table_text = '\n'.join(table_lines)
                    table_data = self._parse_table_from_text(table_text)
                    if table_data:
                        story.extend(self._create_table_with_caption(table_data, "Research Data", is_chinese=is_chinese))
                    table_lines = []
                    in_table = False
                continue
            
            if line_stripped.startswith('|') and '|' in line_stripped[1:]:
                in_table = True
                table_lines.append(line_stripped)
                continue
            elif in_table:
                if table_lines:
                    table_text = '\n'.join(table_lines)
                    table_data = self._parse_table_from_text(table_text)
                    if table_data:
                        story.extend(self._create_table_with_caption(table_data, "Research Data", is_chinese=is_chinese))
                table_lines = []
                in_table = False
            
            if line_stripped.startswith('# '):
                text = line_stripped[2:].replace('**', '').replace('*', '')
                text = self._escape_xml(text)
                current_section = line_stripped[2:].lower()
                in_references = 'reference' in current_section.lower()
                
                story.append(PageBreak())
                story.append(Paragraph(text if is_chinese else text.upper(), custom['h1']))
                after_heading = True
                
                section_key = current_section.split()[0] if current_section else ""
                for key in image_distribution:
                    if section_key in key or key in section_key:
                        if key not in section_image_idx:
                            section_image_idx[key] = 0
                        if section_image_idx[key] < len(image_distribution[key]):
                            img = image_distribution[key][section_image_idx[key]]
                            story.extend(self._create_figure_with_caption(
                                img['path'], img['title'], img['source'], is_chinese=is_chinese
                            ))
                            section_image_idx[key] += 1
                        break
                
            elif line_stripped.startswith('## '):
                text = line_stripped[3:].replace('**', '').replace('*', '')
                text = self._escape_xml(text)
                story.append(Paragraph(text, custom['h2']))
                after_heading = True
                
            elif line_stripped.startswith('### '):
                text = line_stripped[4:].replace('**', '').replace('*', '')
                text = self._escape_xml(text)
                story.append(Paragraph(text, custom['h3']))
                after_heading = True
                
            elif line_stripped.startswith('- ') or line_stripped.startswith('* '):
                text = line_stripped[2:]
                text = self._escape_xml(text)
                story.append(Paragraph(f"• {text}", custom['bullet']))
                after_heading = False
                
            elif re.match(r'^\d+\.\s', line_stripped):
                match = re.match(r'^(\d+)\.\s(.*)$', line_stripped)
                if match:
                    num, text = match.groups()
                    text = self._escape_xml(text)
                    story.append(Paragraph(f"{num}. {text}", custom['numbered']))
                after_heading = False
                
            elif line_stripped.startswith('[TABLE:') or line_stripped.startswith('[IMAGE:'):
                continue
            
            elif line_stripped.startswith('[RENDERED_MERMAID_IMAGE:'):
                img_match = re.match(r'\[RENDERED_MERMAID_IMAGE:(.+?)\|(.+?)\]', line_stripped)
                if img_match:
                    rendered_img_path = img_match.group(1).strip()
                    diagram_type = img_match.group(2).strip()
                    if os.path.exists(rendered_img_path):
                        story.extend(self._create_figure_with_caption(
                            rendered_img_path,
                            diagram_type,
                            "Generated Diagram",
                            is_chinese=is_chinese
                        ))
                continue
            
            elif line_stripped.startswith('[MERMAID:'):
                mermaid_info = self._parse_mermaid_marker(line_stripped)
                if mermaid_info:
                    mermaid_type, mermaid_desc = mermaid_info
                    context = "\n".join(lines[max(0, i-10):i])
                    img_path = self._render_mermaid_to_image(mermaid_type, mermaid_desc, context)
                    if img_path:
                        story.extend(self._create_figure_with_caption(
                            img_path, 
                            mermaid_desc, 
                            f"Generated {mermaid_type.title()} Diagram",
                            is_chinese=is_chinese
                        ))
                continue
                
            else:
                text = self._escape_xml(line_stripped)
                if in_references:
                    story.append(Paragraph(text, custom['reference']))
                elif after_heading:
                    story.append(Paragraph(text, custom['body_first']))
                    after_heading = False
                else:
                    story.append(Paragraph(text, custom['body']))
        
        if in_table and table_lines:
            table_text = '\n'.join(table_lines)
            table_data = self._parse_table_from_text(table_text)
            if table_data:
                story.extend(self._create_table_with_caption(table_data, "Research Data", is_chinese=is_chinese))
        
        story.append(Spacer(1, 24))
        if is_chinese:
            footer_style = custom.get('body', base_styles['Normal'])
            story.append(Paragraph(
                "本报告由 RAAA（需求分析智能体助手）深度研究系统自动生成",
                footer_style
            ))
        else:
            story.append(Paragraph(
                "<i>This report was generated by Requirements Analysis Agent Assistant (RAAA)</i>",
                base_styles['Normal']
            ))
        
        doc.build(story)
        logger.info(f"PDF report generated: {pdf_path}")
        return str(pdf_path)
    
    def _escape_xml(self, text: str) -> str:
        """Escape XML special characters while preserving some formatting."""
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
        return text
    
    def _set_word_run_font(self, run, font_latin: str, font_size_pt: float, 
                           is_chinese: bool = False, bold: bool = False, italic: bool = False,
                           font_east_asia: str = None):
        """
        Set font properties on a Word run, including East Asian font for Chinese.
        python-docx requires XML manipulation to set East Asian fonts properly.
        """
        from docx.shared import Pt
        from docx.oxml.ns import qn
        
        run.font.name = font_latin
        run.font.size = Pt(font_size_pt)
        if bold:
            run.bold = True
        if italic:
            run.italic = True
        
        if is_chinese and font_east_asia:
            # 设置东亚字体（python-docx 不直接支持，需要操作 XML）
            rPr = run._element.get_or_add_rPr()
            rFonts = rPr.find(qn('w:rFonts'))
            if rFonts is None:
                rFonts = run._element.makeelement(qn('w:rFonts'), {})
                rPr.insert(0, rFonts)
            rFonts.set(qn('w:eastAsia'), font_east_asia)
    
    def _set_paragraph_line_spacing(self, para, line_spacing: float = 1.5):
        """Set paragraph line spacing (e.g., 1.5 for 1.5倍行距)."""
        from docx.shared import Pt
        from docx.oxml.ns import qn
        
        pPr = para._element.get_or_add_pPr()
        spacing = pPr.find(qn('w:spacing'))
        if spacing is None:
            spacing = para._element.makeelement(qn('w:spacing'), {})
            pPr.append(spacing)
        # line spacing in 240ths of a line
        spacing.set(qn('w:line'), str(int(240 * line_spacing)))
        spacing.set(qn('w:lineRule'), 'auto')
    
    def _add_page_number(self, doc):
        """Add page number to footer (right-aligned, Arabic numerals)."""
        from docx.oxml.ns import qn
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        
        try:
            section = doc.sections[-1]
            footer = section.footer
            footer.is_linked_to_previous = False
            
            para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
            para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            
            # 添加页码域代码
            run = para.add_run()
            run.font.size = Pt(9)
            fldChar1 = run._element.makeelement(qn('w:fldChar'), {qn('w:fldCharType'): 'begin'})
            run._element.append(fldChar1)
            
            run2 = para.add_run()
            run2.font.size = Pt(9)
            instrText = run2._element.makeelement(qn('w:instrText'), {})
            instrText.text = ' PAGE '
            run2._element.append(instrText)
            
            run3 = para.add_run()
            run3.font.size = Pt(9)
            fldChar2 = run3._element.makeelement(qn('w:fldChar'), {qn('w:fldCharType'): 'end'})
            run3._element.append(fldChar2)
        except Exception as e:
            logger.debug(f"Failed to add page number: {e}")

    def _generate_word(self, title: str, content: str, filename: str = None,
                       images: List[Dict] = None, tables: List[Dict] = None) -> str:
        """Generate Word document with academic formatting."""
        try:
            from docx import Document
            from docx.shared import Inches, Pt, Cm
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.enum.style import WD_STYLE_TYPE
        except ImportError:
            logger.warning("python-docx not installed. Word generation skipped.")
            return ""
        
        images = images or []
        is_chinese = self._is_chinese_content(title) or self._is_chinese_content(content[:500])
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"research_report_{timestamp}"
        if filename.endswith('.pdf'):
            filename = filename[:-4]
        
        docx_path = self.output_dir / f"{filename}.docx"
        
        doc = Document()
        
        # 页面设置
        sections = doc.sections
        for section in sections:
            if is_chinese:
                # A4纸，左右2.6cm，上下3cm
                section.top_margin = Cm(3)
                section.bottom_margin = Cm(3)
                section.left_margin = Cm(2.6)
                section.right_margin = Cm(2.6)
            else:
                section.top_margin = Cm(2.54)
                section.bottom_margin = Cm(2.54)
                section.left_margin = Cm(2.54)
                section.right_margin = Cm(2.54)
        
        # 字体配置
        if is_chinese:
            font_title = 'SimHei'       # 黑体
            font_author = 'KaiTi'       # 楷体
            font_heading = 'SimSun'     # 宋体
            font_body = 'SimSun'        # 宋体
            font_latin = 'Times New Roman'
            body_size = 12              # 小四号
            h1_size = 14                # 四号
            h2_size = 12                # 小四号
            h3_size = 12                # 小四号
            h4_size = 12                # 小四号
            title_size = 22             # 二号
            author_size = 14            # 四号
            ref_size = 10.5             # 五号
            conclusion_size = 10.5      # 五号
        else:
            font_title = 'Times New Roman'
            font_author = 'Times New Roman'
            font_heading = 'Times New Roman'
            font_body = 'Times New Roman'
            font_latin = 'Times New Roman'
            body_size = 10
            h1_size = 14
            h2_size = 12
            h3_size = 11
            h4_size = 10
            title_size = 16
            author_size = 11
            ref_size = 9
            conclusion_size = 10
        
        # === 标题（二号黑体，居中，加粗） ===
        title_para = doc.add_paragraph()
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title_para.add_run(title)
        self._set_word_run_font(title_run, font_latin, title_size, 
                                is_chinese=is_chinese, bold=True, font_east_asia=font_title)
        self._set_paragraph_line_spacing(title_para, 1.5)
        
        # === 作者/团队（四号楷体，居中） ===
        author_para = doc.add_paragraph()
        author_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if is_chinese:
            author_run = author_para.add_run("RAAA 深度研究系统")
        else:
            author_run = author_para.add_run("Generated by RAAA Deep Research")
        self._set_word_run_font(author_run, font_latin, author_size,
                                is_chinese=is_chinese, font_east_asia=font_author)
        self._set_paragraph_line_spacing(author_para, 1.5)
        
        # === 日期 ===
        date_para = doc.add_paragraph()
        date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if is_chinese:
            date_run = date_para.add_run(datetime.now().strftime("%Y年%m月%d日"))
        else:
            date_run = date_para.add_run(datetime.now().strftime("%B %d, %Y"))
        self._set_word_run_font(date_run, font_latin, body_size,
                                is_chinese=is_chinese, italic=not is_chinese, font_east_asia=font_body)
        self._set_paragraph_line_spacing(date_para, 1.5)
        
        doc.add_paragraph()
        
        # 添加页码
        self._add_page_number(doc)
        
        downloaded_images = self._prepare_images(images, max_images=8)
        img_idx = 0
        in_table = False
        table_lines = []
        in_references = False
        
        content = self._process_mermaid_code_blocks(content)
        
        lines = content.split('\n')
        for line in lines:
            line_stripped = line.strip()
            
            if not line_stripped:
                if in_table and table_lines:
                    self._add_word_table(doc, table_lines, is_chinese=is_chinese)
                    table_lines = []
                    in_table = False
                continue
            
            if line_stripped.startswith('|') and '|' in line_stripped[1:]:
                in_table = True
                table_lines.append(line_stripped)
                continue
            elif in_table:
                if table_lines:
                    self._add_word_table(doc, table_lines, is_chinese=is_chinese)
                table_lines = []
                in_table = False
            
            if line_stripped.startswith('# '):
                text = line_stripped[2:].replace('**', '').replace('*', '')
                in_references = 'reference' in text.lower() or '参考文献' in text
                doc.add_page_break()
                # 一级标题（四号宋体/黑体，加粗，顶格）
                if is_chinese:
                    heading = doc.add_paragraph()
                    heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    run = heading.add_run(text)
                    self._set_word_run_font(run, font_latin, h1_size,
                                            is_chinese=True, bold=True, font_east_asia=font_heading)
                    self._set_paragraph_line_spacing(heading, 1.5)
                else:
                    heading = doc.add_heading(text.upper(), level=1)
                    for run in heading.runs:
                        run.font.name = font_latin
                        run.font.size = Pt(h1_size)
                
                if img_idx < len(downloaded_images):
                    self._add_word_image(doc, downloaded_images[img_idx], is_chinese=is_chinese)
                    img_idx += 1
                    
            elif line_stripped.startswith('## '):
                text = line_stripped[3:].replace('**', '').replace('*', '')
                # 二级标题（小四号宋体/黑体，加粗，顶格）
                if is_chinese:
                    heading = doc.add_paragraph()
                    heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    run = heading.add_run(text)
                    self._set_word_run_font(run, font_latin, h2_size,
                                            is_chinese=True, bold=True, font_east_asia=font_heading)
                    self._set_paragraph_line_spacing(heading, 1.5)
                else:
                    heading = doc.add_heading(text, level=2)
                    for run in heading.runs:
                        run.font.name = font_latin
                        run.font.size = Pt(h2_size)
                    
            elif line_stripped.startswith('### '):
                text = line_stripped[4:].replace('**', '').replace('*', '')
                # 三级标题（小四号宋体/黑体，加粗，顶格）
                if is_chinese:
                    heading = doc.add_paragraph()
                    heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    run = heading.add_run(text)
                    self._set_word_run_font(run, font_latin, h3_size,
                                            is_chinese=True, bold=True, font_east_asia=font_heading)
                    self._set_paragraph_line_spacing(heading, 1.5)
                else:
                    heading = doc.add_heading(text, level=3)
                    for run in heading.runs:
                        run.font.name = font_latin
                        run.font.size = Pt(h3_size)

            elif line_stripped.startswith('#### '):
                text = line_stripped[5:].replace('**', '').replace('*', '')
                # 四级标题（小四号宋体/黑体，加粗，顶格）
                if is_chinese:
                    heading = doc.add_paragraph()
                    heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    run = heading.add_run(text)
                    self._set_word_run_font(run, font_latin, h4_size,
                                            is_chinese=True, bold=True, font_east_asia=font_heading)
                    self._set_paragraph_line_spacing(heading, 1.5)
                else:
                    para = doc.add_paragraph()
                    run = para.add_run(text)
                    run.bold = True
                    run.font.name = font_latin
                    run.font.size = Pt(h4_size)
                    
            elif line_stripped.startswith('- ') or line_stripped.startswith('* '):
                text = line_stripped[2:].replace('**', '').replace('*', '')
                para = doc.add_paragraph(text, style='List Bullet')
                for run in para.runs:
                    self._set_word_run_font(run, font_latin, body_size,
                                            is_chinese=is_chinese, font_east_asia=font_body)
                self._set_paragraph_line_spacing(para, 1.5)
                    
            elif re.match(r'^\d+\.\s', line_stripped):
                match = re.match(r'^(\d+)\.\s(.*)$', line_stripped)
                if match:
                    _, text = match.groups()
                    text = text.replace('**', '').replace('*', '')
                    para = doc.add_paragraph(text, style='List Number')
                    for run in para.runs:
                        self._set_word_run_font(run, font_latin, body_size,
                                                is_chinese=is_chinese, font_east_asia=font_body)
                    self._set_paragraph_line_spacing(para, 1.5)
                        
            elif line_stripped.startswith('[TABLE:') or line_stripped.startswith('[IMAGE:'):
                continue
            
            elif line_stripped.startswith('[RENDERED_MERMAID_IMAGE:'):
                img_match = re.match(r'\[RENDERED_MERMAID_IMAGE:(.+?)\|(.+?)\]', line_stripped)
                if img_match:
                    rendered_img_path = img_match.group(1).strip()
                    diagram_type = img_match.group(2).strip()
                    if os.path.exists(rendered_img_path):
                        self._add_word_image(doc, {
                            'path': rendered_img_path,
                            'title': diagram_type,
                            'source': "Generated Diagram"
                        }, is_chinese=is_chinese)
                continue
            
            elif line_stripped.startswith('[MERMAID:'):
                mermaid_info = self._parse_mermaid_marker(line_stripped)
                if mermaid_info:
                    mermaid_type, mermaid_desc = mermaid_info
                    context = "\n".join(lines[max(0, lines.index(line)-10):lines.index(line)])
                    img_path = self._render_mermaid_to_image(mermaid_type, mermaid_desc, context)
                    if img_path:
                        self._add_word_image(doc, {
                            'path': img_path,
                            'title': mermaid_desc,
                            'source': f"Generated {mermaid_type.title()} Diagram"
                        }, is_chinese=is_chinese)
                continue
                
            else:
                text = line_stripped.replace('**', '').replace('*', '')
                para = doc.add_paragraph()
                if is_chinese:
                    # 正文首行缩进两字符
                    para.paragraph_format.first_line_indent = Cm(0.74)  # 约两个中文字符
                para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                run = para.add_run(text)
                if in_references:
                    self._set_word_run_font(run, font_latin, ref_size,
                                            is_chinese=is_chinese, font_east_asia=font_body)
                else:
                    self._set_word_run_font(run, font_latin, body_size,
                                            is_chinese=is_chinese, font_east_asia=font_body)
                self._set_paragraph_line_spacing(para, 1.5)
        
        if in_table and table_lines:
            self._add_word_table(doc, table_lines, is_chinese=is_chinese)
        
        doc.add_paragraph()
        footer = doc.add_paragraph()
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if is_chinese:
            footer_run = footer.add_run("本报告由 RAAA（需求分析智能体助手）深度研究系统自动生成")
            self._set_word_run_font(footer_run, font_latin, 9,
                                    is_chinese=True, italic=True, font_east_asia=font_body)
        else:
            footer_run = footer.add_run("This report was generated by Requirements Analysis Agent Assistant (RAAA)")
            footer_run.italic = True
            footer_run.font.size = Pt(9)
        
        doc.save(str(docx_path))
        logger.info(f"Word document generated: {docx_path}")
        return str(docx_path)
    
    def _add_word_table(self, doc, table_lines: List[str], is_chinese: bool = False):
        """
        Add a table to Word document from markdown table lines.
        For Chinese: uses 三线表 (three-line table) style with Chinese fonts.
        """
        try:
            from docx.shared import Pt, Inches, Cm
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml.ns import nsdecls, qn
            from docx.oxml import parse_xml
            
            table_data = self._parse_table_from_text('\n'.join(table_lines))
            if not table_data:
                return
            
            table_num = self._next_table_num()
            caption = doc.add_paragraph()
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if is_chinese:
                caption_run = caption.add_run(f"表{table_num}")
                self._set_word_run_font(caption_run, 'Times New Roman', 9,
                                        is_chinese=True, bold=True, font_east_asia='SimHei')
            else:
                caption_run = caption.add_run(f"Table {table_num}. Research Data")
                caption_run.bold = True
                caption_run.font.size = Pt(9)
            
            table = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
            
            if is_chinese:
                # 三线表样式：仅顶线、表头下线、底线
                table.style = 'Table Grid'
                # 移除所有边框，然后只添加三线
                tbl = table._tbl
                tblPr = tbl.tblPr if tbl.tblPr is not None else tbl._add_tblPr()
                borders = parse_xml(
                    f'<w:tblBorders {nsdecls("w")}>'
                    '  <w:top w:val="single" w:sz="12" w:space="0" w:color="000000"/>'
                    '  <w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                    '  <w:bottom w:val="single" w:sz="12" w:space="0" w:color="000000"/>'
                    '  <w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                    '  <w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                    '  <w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                    '</w:tblBorders>'
                )
                # 移除旧边框
                old_borders = tblPr.find(qn('w:tblBorders'))
                if old_borders is not None:
                    tblPr.remove(old_borders)
                tblPr.append(borders)
                
                # 在表头行下方添加细线
                if len(table_data) > 1:
                    header_row = table.rows[0]
                    for cell in header_row.cells:
                        tcPr = cell._element.get_or_add_tcPr()
                        tcBorders = parse_xml(
                            f'<w:tcBorders {nsdecls("w")}>'
                            '  <w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
                            '</w:tcBorders>'
                        )
                        old_tcBorders = tcPr.find(qn('w:tcBorders'))
                        if old_tcBorders is not None:
                            tcPr.remove(old_tcBorders)
                        tcPr.append(tcBorders)
            else:
                table.style = 'Table Grid'
            
            font_body = 'SimSun' if is_chinese else 'Times New Roman'
            
            for i, row_data in enumerate(table_data):
                row = table.rows[i]
                for j, cell_text in enumerate(row_data):
                    cell = row.cells[j]
                    clean_text = str(cell_text)
                    clean_text = re.sub(r'^\*+|\*+$', '', clean_text)
                    clean_text = re.sub(r'\*\*(.+?)\*\*', r'\1', clean_text)
                    clean_text = re.sub(r'\*(.+?)\*', r'\1', clean_text)
                    cell.text = clean_text.strip()
                    for para in cell.paragraphs:
                        # 表内数字上下对齐
                        para.alignment = WD_ALIGN_PARAGRAPH.CENTER if i == 0 else WD_ALIGN_PARAGRAPH.LEFT
                        for run in para.runs:
                            self._set_word_run_font(run, 'Times New Roman', 9,
                                                    is_chinese=is_chinese, bold=(i == 0),
                                                    font_east_asia=font_body)
            
            doc.add_paragraph()
            
        except Exception as e:
            logger.warning(f"Failed to add Word table: {e}")
    
    def _add_word_image(self, doc, img_info: Dict, is_chinese: bool = False):
        """Add an image with caption to Word document."""
        try:
            from docx.shared import Inches, Pt
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            
            fig_num = self._next_figure_num()
            
            para = doc.add_paragraph()
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = para.add_run()
            run.add_picture(img_info['path'], width=Inches(5.0))
            
            caption = doc.add_paragraph()
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if is_chinese:
                caption_text = f"图{fig_num} {img_info.get('title', '')}"
                if img_info.get('source') and img_info['source'] != 'Unknown':
                    caption_text += f"（来源：{img_info['source']}）"
                caption_run = caption.add_run(caption_text)
                self._set_word_run_font(caption_run, 'Times New Roman', 9,
                                        is_chinese=True, font_east_asia='SimHei')
            else:
                caption_text = f"Figure {fig_num}. {img_info.get('title', '')} (Source: {img_info.get('source', 'Unknown')})"
                caption_run = caption.add_run(caption_text)
                caption_run.font.size = Pt(9)
                caption_run.font.name = 'Times New Roman'
            
        except Exception as e:
            logger.warning(f"Failed to add Word image: {e}")


class PDFReportGenerator(AcademicReportGenerator):
    """Backward-compatible alias for AcademicReportGenerator."""
    pass
