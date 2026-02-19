from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
import os

def create_chinese_new_year_food_presentation():
    # Create a new presentation
    prs = Presentation()
    
    # Set slide width and height (standard 4:3 aspect ratio)
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)
    
    # Title Slide
    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    title = slide.shapes.title
    subtitle = slide.placeholders[1]
    
    title.text = "春节美食之旅"
    subtitle.text = "传统年味，舌尖上的中国"
    
    # Change title style
    title.text_frame.paragraphs[0].font.size = Pt(44)
    title.text_frame.paragraphs[0].font.color.rgb = RGBColor(139, 0, 0)  # Dark red
    subtitle.text_frame.paragraphs[0].font.size = Pt(24)
    subtitle.text_frame.paragraphs[0].font.color.rgb = RGBColor(128, 128, 128)  # Gray
    
    # Slide 2: Introduction
    bullet_slide_layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(bullet_slide_layout)
    shapes = slide.shapes
    title_shape = shapes.title
    body_shape = shapes.placeholders[1]
    
    title_shape.text = '春节饮食文化'
    
    text_frame = body_shape.text_frame
    text_frame.clear()  # Clear placeholder text
    p = text_frame.paragraphs[0]
    p.text = "春节饮食不仅是味蕾的享受，更是文化的传承。"
    p.font_size = Pt(18)
    
    p = text_frame.add_paragraph()
    p.text = "每道菜都蕴含着吉祥寓意"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "团圆饭是春节的核心"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "地域差异带来丰富口味"
    p.level = 1
    p.font_size = Pt(16)
    
    # Slide 3: Northern Chinese Food
    slide = prs.slides.add_slide(bullet_slide_layout)
    shapes = slide.shapes
    title_shape = shapes.title
    body_shape = shapes.placeholders[1]
    
    title_shape.text = '北方春节美食'
    
    text_frame = body_shape.text_frame
    text_frame.clear()
    p = text_frame.paragraphs[0]
    p.text = "饺子 - 更岁交子，财源滚滚"
    p.font_size = Pt(18)
    
    p = text_frame.add_paragraph()
    p.text = "年糕 - 年年高升，步步登高"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "炖菜 - 温暖丰盛，团团圆圆"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "腊八蒜 - 酸甜爽口，开胃解腻"
    p.level = 1
    p.font_size = Pt(16)
    
    # Slide 4: Southern Chinese Food
    slide = prs.slides.add_slide(bullet_slide_layout)
    shapes = slide.shapes
    title_shape = shapes.title
    body_shape = shapes.placeholders[1]
    
    title_shape.text = '南方春节美食'
    
    text_frame = body_shape.text_frame
    text_frame.clear()
    p = text_frame.paragraphs[0]
    p.text = "汤圆 - 团团圆圆，甜蜜美满"
    p.font_size = Pt(18)
    
    p = text_frame.add_paragraph()
    p.text = "年糕 - 年年高升，财运亨通"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "白切鸡 - 吉祥如意，大吉大利"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "盆菜 - 丰盛富足，盆满钵满"
    p.level = 1
    p.font_size = Pt(16)
    
    # Slide 5: Main dishes
    slide = prs.slides.add_slide(bullet_slide_layout)
    shapes = slide.shapes
    title_shape = shapes.title
    body_shape = shapes.placeholders[1]
    
    title_shape.text = '春节主菜'
    
    text_frame = body_shape.text_frame
    text_frame.clear()
    p = text_frame.paragraphs[0]
    p.text = "鱼 - 年年有余"
    p.font_size = Pt(18)
    
    p = text_frame.add_paragraph()
    p.text = "红烧肉 - 红红火火"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "四喜丸子 - 四季平安"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "白切鸡 - 大吉大利"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "肘子 - 有头有尾，圆满收尾"
    p.level = 1
    p.font_size = Pt(16)
    
    # Slide 6: Desserts & Snacks
    slide = prs.slides.add_slide(bullet_slide_layout)
    shapes = slide.shapes
    title_shape = shapes.title
    body_shape = shapes.placeholders[1]
    
    title_shape.text = '春节甜品与零食'
    
    text_frame = body_shape.text_frame
    text_frame.clear()
    p = text_frame.paragraphs[0]
    p.text = "糖果 - 甜甜蜜蜜"
    p.font_size = Pt(18)
    
    p = text_frame.add_paragraph()
    p.text = "瓜子花生 - 生生不息"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "八宝饭 - 八宝齐聚，福寿安康"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "糖葫芦 - 红红火火"
    p.level = 1
    p.font_size = Pt(16)
    
    # Slide 7: Drinks
    slide = prs.slides.add_slide(bullet_slide_layout)
    shapes = slide.shapes
    title_shape = shapes.title
    body_shape = shapes.placeholders[1]
    
    title_shape.text = '春节饮品'
    
    text_frame = body_shape.text_frame
    text_frame.clear()
    p = text_frame.paragraphs[0]
    p.text = "茶 - 消食解腻，清心养神"
    p.font_size = Pt(18)
    
    p = text_frame.add_paragraph()
    p.text = "黄酒 - 温润醇香，暖身暖心"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "白酒 - 辞旧迎新，增进感情"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "果汁 - 营养健康，老少皆宜"
    p.level = 1
    p.font_size = Pt(16)
    
    # Slide 8: Regional Specialties
    slide = prs.slides.add_slide(bullet_slide_layout)
    shapes = slide.shapes
    title_shape = shapes.title
    body_shape = shapes.placeholders[1]
    
    title_shape.text = '地方特色'
    
    text_frame = body_shape.text_frame
    text_frame.clear()
    p = text_frame.paragraphs[0]
    p.text = "四川 - 麻辣火锅，热闹红火"
    p.font_size = Pt(18)
    
    p = text_frame.add_paragraph()
    p.text = "广东 - 早茶点心，精致美味"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "北京 - 烤鸭涮肉，京味十足"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "江浙 - 小笼包、松鼠桂鱼，精致清淡"
    p.level = 1
    p.font_size = Pt(16)
    
    # Slide 9: Modern Trends
    slide = prs.slides.add_slide(bullet_slide_layout)
    shapes = slide.shapes
    title_shape = shapes.title
    body_shape = shapes.placeholders[1]
    
    title_shape.text = '现代春节饮食趋势'
    
    text_frame = body_shape.text_frame
    text_frame.clear()
    p = text_frame.paragraphs[0]
    p.text = "外卖年夜饭 - 方便快捷"
    p.font_size = Pt(18)
    
    p = text_frame.add_paragraph()
    p.text = "健康饮食 - 少油少盐，营养均衡"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "融合菜式 - 传统与创新结合"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "国际化 - 引入异国风味"
    p.level = 1
    p.font_size = Pt(16)
    
    # Slide 10: Conclusion
    slide = prs.slides.add_slide(bullet_slide_layout)
    shapes = slide.shapes
    title_shape = shapes.title
    body_shape = shapes.placeholders[1]
    
    title_shape.text = '春节饮食总结'
    
    text_frame = body_shape.text_frame
    text_frame.clear()
    p = text_frame.paragraphs[0]
    p.text = "春节饮食承载着深厚的文化内涵"
    p.font_size = Pt(18)
    
    p = text_frame.add_paragraph()
    p.text = "传统与现代的完美结合"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "家人团聚的重要纽带"
    p.level = 1
    p.font_size = Pt(16)
    
    p = text_frame.add_paragraph()
    p.text = "美好祝愿的象征"
    p.level = 1
    p.font_size = Pt(16)
    
    # Save the presentation
    file_path = '/Users/xuan.lx/Documents/x-agent/x-agent/workspace/chinese_new_year_food_presentation.pptx'
    prs.save(file_path)
    return file_path

if __name__ == '__main__':
    file_path = create_chinese_new_year_food_presentation()
    print(f"春节美食PPT已创建完成: {file_path}")