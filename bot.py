import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.exc import IntegrityError

# ================== إعدادات ==================
BOT_TOKEN = "8079685928:AAGUFTDfS851OwQHf8aQ5kZAFfYlb3NVYnM"
ADMIN_IDS = {833001594}  # ضع معرفات الإدمن هنا

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

Base = declarative_base()
engine = create_engine("sqlite:///college.db", connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)

STATE = {}  # لتتبع خطوات الإدمن

# ================== الجداول ==================
class Level(Base):
    __tablename__ = "levels"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    subjects = relationship("Subject", back_populates="level", cascade="all, delete-orphan")

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    level_id = Column(Integer, ForeignKey("levels.id", ondelete="CASCADE"), nullable=False)
    level = relationship("Level", back_populates="subjects")
    sections = relationship("Section", back_populates="subject", cascade="all, delete-orphan")

class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    subject = relationship("Subject", back_populates="sections")
    items = relationship("Item", back_populates="section", cascade="all, delete-orphan")

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    section = relationship("Section", back_populates="items")
    contents = relationship("Content", back_populates="item", cascade="all, delete-orphan")

class Content(Base):
    __tablename__ = "contents"
    id = Column(Integer, primary_key=True)
    type = Column(String, nullable=False)  # text / file
    value = Column(Text, nullable=False)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    item = relationship("Item", back_populates="contents")

Base.metadata.create_all(engine)

# ================== وظائف مساعدة ==================
def is_admin(uid):
    return uid in ADMIN_IDS

def get_admin_keyboard():
    """لوحة تحكم الإدارة"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة مستوى", callback_data="add_level")],
        [InlineKeyboardButton("🛠 إدارة الهيكل", callback_data="manage")],
        [InlineKeyboardButton("🗑 حذف عناصر", callback_data="delete_menu")]
    ])

# ================== أوامر الطلاب ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        s = Session()
        levels = s.query(Level).all()
        
        if not levels:
            message_text = "📚 لا توجد مستويات متاحة حالياً."
            kb = []
        else:
            message_text = "📚 اختر المستوى:"
            kb = [[InlineKeyboardButton(l.name, callback_data=f"lvl:{l.id}")] for l in levels]
        
        reply_markup = InlineKeyboardMarkup(kb) if kb else None
        
        # التحقق إذا كان الاستدعاء من Message أم CallbackQuery
        if update.message:
            await update.message.reply_text(message_text, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Error in start: {e}")
        error_msg = "❌ حدث خطأ. يرجى المحاولة لاحقاً."
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.callback_query:
            await update.callback_query.message.reply_text(error_msg)
    finally:
        s.close()

# ================== لوحة الإدارة ==================
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): 
        await update.message.reply_text("⛔ ليس لديك صلاحية الوصول.")
        return
    await update.message.reply_text("🛠 لوحة الإدارة", reply_markup=get_admin_keyboard())

# ================== التعامل مع الأزرار ==================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data
    s = Session()
    
    try:
        # ---------- طالب ----------
        if data.startswith("lvl:"):
            lvl_id = int(data[4:])
            subs = s.query(Subject).filter_by(level_id=lvl_id).all()
            if not subs:
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_start")]]
                await q.edit_message_text("⚠️ لا توجد مواد في هذا المستوى.", reply_markup=InlineKeyboardMarkup(kb))
                return
            kb = [[InlineKeyboardButton(x.name, callback_data=f"sub:{x.id}")] for x in subs]
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_start")])
            await q.edit_message_text("اختر المادة:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("sub:"):
            sub_id = int(data[4:])
            secs = s.query(Section).filter_by(subject_id=sub_id).all()
            if not secs:
                subject = s.query(Subject).filter_by(id=sub_id).first()
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=f"lvl:{subject.level_id}")]]
                await q.edit_message_text("⚠️ لا توجد أقسام في هذه المادة.", reply_markup=InlineKeyboardMarkup(kb))
                return
            kb = [[InlineKeyboardButton(x.name, callback_data=f"sec:{x.id}")] for x in secs]
            lvl_id = s.query(Subject).filter_by(id=sub_id).first().level_id
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"lvl:{lvl_id}")])
            await q.edit_message_text("اختر القسم:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("sec:"):
            sec_id = int(data[4:])
            items = s.query(Item).filter_by(section_id=sec_id).all()
            if not items:
                section = s.query(Section).filter_by(id=sec_id).first()
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=f"sub:{section.subject_id}")]]
                await q.edit_message_text("⚠️ لا توجد عناصر في هذا القسم.", reply_markup=InlineKeyboardMarkup(kb))
                return
            kb = [[InlineKeyboardButton(x.name, callback_data=f"item:{x.id}")] for x in items]
            sub_id = s.query(Section).filter_by(id=sec_id).first().subject_id
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"sub:{sub_id}")])
            await q.edit_message_text("اختر العنصر:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("item:"):
            item_id = int(data[5:])
            contents = s.query(Content).filter_by(item_id=item_id).all()
            
            # إرسال محتويات جديدة في رسائل منفصلة
            if not contents:
                await q.message.reply_text("⚠️ لا يوجد محتوى لهذا العنصر.")
            else:
                for c in contents:
                    try:
                        if c.type == "text": 
                            await q.message.reply_text(c.value)
                        else: 
                            await q.message.reply_document(c.value)
                    except Exception as e:
                        logger.error(f"Error sending content {c.id}: {e}")
                        await q.message.reply_text(f"⚠️ خطأ في إرسال المحتوى: {str(e)[:50]}")
            
            # العودة إلى القسم
            item = s.query(Item).filter_by(id=item_id).first()
            if item:
                sec_id = item.section_id
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=f"sec:{sec_id}")]]
                await q.message.reply_text("اختر:", reply_markup=InlineKeyboardMarkup(kb))

        # ---------- إدمن - إضافة ----------
        elif data == "add_level":
            if not is_admin(uid): return
            STATE[uid] = {"step": "level"}
            await q.message.reply_text("✏️ أرسل اسم المستوى الجديد")

        elif data == "manage":
            if not is_admin(uid): return
            STATE[uid] = {"step": "choose_level"}
            lvls = s.query(Level).all()
            if not lvls:
                await q.message.reply_text("⚠️ لا توجد مستويات. أضف مستوى أولاً.")
                return
            kb = [[InlineKeyboardButton(l.name, callback_data=f"m_lvl:{l.id}")] for l in lvls]
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_admin")])
            await q.message.reply_text("اختر مستوى:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("m_lvl:"):
            if not is_admin(uid): return
            STATE[uid] = {"level": int(data[6:]), "step": "subject"}
            await q.message.reply_text("✏️ أرسل اسم المادة الجديدة")

        elif data.startswith("m_sub:"):
            if not is_admin(uid): return
            STATE[uid] = {"subject": int(data[6:]), "step": "section"}
            await q.message.reply_text("✏️ أرسل اسم القسم الجديد")

        elif data.startswith("m_sec:"):
            if not is_admin(uid): return
            STATE[uid] = {"section": int(data[6:]), "step": "item"}
            await q.message.reply_text("✏️ أرسل اسم العنصر الجديد")

        elif data.startswith("m_item:"):
            if not is_admin(uid): return
            STATE[uid] = {"item": int(data[7:]), "step": "content"}
            await q.message.reply_text("📎 أرسل المحتوى (نص، ملف PDF، صورة، فيديو)")

        # ---------- إدمن - حذف ----------
        elif data == "delete_menu":
            if not is_admin(uid): return
            kb = [
                [InlineKeyboardButton("🗑 حذف مستوى", callback_data="del_level")],
                [InlineKeyboardButton("🗑 حذف مادة", callback_data="del_subject")],
                [InlineKeyboardButton("🗑 حذف قسم", callback_data="del_section")],
                [InlineKeyboardButton("🗑 حذف عنصر", callback_data="del_item")],
                [InlineKeyboardButton("🗑 حذف محتوى", callback_data="del_content")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_admin")]
            ]
            await q.edit_message_text("🔧 قائمة الحذف:", reply_markup=InlineKeyboardMarkup(kb))

        elif data == "del_level":
            if not is_admin(uid): return
            lvls = s.query(Level).all()
            if not lvls:
                await q.message.reply_text("⚠️ لا توجد مستويات للحذف.")
                return
            kb = [[InlineKeyboardButton(f"🗑 {l.name}", callback_data=f"del_lvl:{l.id}")] for l in lvls]
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="delete_menu")])
            await q.message.reply_text("اختر مستوى للحذف:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("del_lvl:"):
            if not is_admin(uid): return
            level_id = int(data[8:])
            level = s.query(Level).filter_by(id=level_id).first()
            if level:
                s.delete(level)
                s.commit()
                await q.message.reply_text(f"✅ تم حذف المستوى: {level.name}")
            else:
                await q.message.reply_text("❌ المستوى غير موجود.")

        elif data == "del_subject":
            if not is_admin(uid): return
            subjects = s.query(Subject).all()
            if not subjects:
                await q.message.reply_text("⚠️ لا توجد مواد للحذف.")
                return
            kb = [[InlineKeyboardButton(f"🗑 {sub.name}", callback_data=f"del_sub:{sub.id}")] for sub in subjects]
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="delete_menu")])
            await q.message.reply_text("اختر مادة للحذف:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("del_sub:"):
            if not is_admin(uid): return
            subject_id = int(data[8:])
            subject = s.query(Subject).filter_by(id=subject_id).first()
            if subject:
                s.delete(subject)
                s.commit()
                await q.message.reply_text(f"✅ تم حذف المادة: {subject.name}")
            else:
                await q.message.reply_text("❌ المادة غير موجودة.")

        elif data == "del_section":
            if not is_admin(uid): return
            sections = s.query(Section).all()
            if not sections:
                await q.message.reply_text("⚠️ لا توجد أقسام للحذف.")
                return
            kb = [[InlineKeyboardButton(f"🗑 {sec.name}", callback_data=f"del_sec:{sec.id}")] for sec in sections]
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="delete_menu")])
            await q.message.reply_text("اختر قسم للحذف:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("del_sec:"):
            if not is_admin(uid): return
            section_id = int(data[8:])
            section = s.query(Section).filter_by(id=section_id).first()
            if section:
                s.delete(section)
                s.commit()
                await q.message.reply_text(f"✅ تم حذف القسم: {section.name}")
            else:
                await q.message.reply_text("❌ القسم غير موجود.")

        elif data == "del_item":
            if not is_admin(uid): return
            items = s.query(Item).all()
            if not items:
                await q.message.reply_text("⚠️ لا توجد عناصر للحذف.")
                return
            kb = [[InlineKeyboardButton(f"🗑 {item.name}", callback_data=f"del_itm:{item.id}")] for item in items]
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="delete_menu")])
            await q.message.reply_text("اختر عنصر للحذف:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("del_itm:"):
            if not is_admin(uid): return
            item_id = int(data[8:])
            item = s.query(Item).filter_by(id=item_id).first()
            if item:
                s.delete(item)
                s.commit()
                await q.message.reply_text(f"✅ تم حذف العنصر: {item.name}")
            else:
                await q.message.reply_text("❌ العنصر غير موجود.")

        elif data == "del_content":
            if not is_admin(uid): return
            contents = s.query(Content).all()
            if not contents:
                await q.message.reply_text("⚠️ لا توجد محتويات للحذف.")
                return
            kb = []
            for content in contents:
                display = f"🗑 {content.type} - {content.value[:30]}..."
                kb.append([InlineKeyboardButton(display, callback_data=f"del_con:{content.id}")])
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="delete_menu")])
            await q.message.reply_text("اختر محتوى للحذف:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("del_con:"):
            if not is_admin(uid): return
            content_id = int(data[8:])
            content = s.query(Content).filter_by(id=content_id).first()
            if content:
                s.delete(content)
                s.commit()
                await q.message.reply_text(f"✅ تم حذف المحتوى ({content.type})")
            else:
                await q.message.reply_text("❌ المحتوى غير موجود.")

        # ---------- رجوع ----------
        elif data == "back_start": 
            # استدعاء start مع update و context
            await start(update, context)
            
        elif data == "back_admin":
            if not is_admin(uid): return
            await q.edit_message_text("🛠 لوحة الإدارة", reply_markup=get_admin_keyboard())

    except IntegrityError as e:
        logger.error(f"Integrity error: {e}")
        await q.message.reply_text("❌ لا يمكن الحذف بسبب وجود عناصر مرتبطة.")
    except Exception as e:
        logger.error(f"Error in callbacks: {e}")
        await q.message.reply_text("❌ حدث خطأ غير متوقع.")
        # لإظهار التفاصيل للمطور (يمكن إزالة هذا في الإصدار النهائي):
        await q.message.reply_text(f"🔧 تفاصيل الخطأ: {str(e)[:100]}")
    finally:
        s.close()

# ================== التعامل مع الرسائل ==================
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in STATE: 
        return
    
    if not is_admin(uid):
        del STATE[uid]
        return
    
    s = Session()
    try:
        step = STATE[uid].get("step")
        
        if step == "level": 
            level_name = update.message.text.strip()
            if not level_name:
                await update.message.reply_text("⚠️ اسم المستوى لا يمكن أن يكون فارغاً.")
                return
                
            new_level = Level(name=level_name)
            s.add(new_level)
            s.commit()
            await update.message.reply_text(f"✅ تم إضافة المستوى: {new_level.name}")
            del STATE[uid]
            
        elif step == "subject": 
            subject_name = update.message.text.strip()
            if not subject_name:
                await update.message.reply_text("⚠️ اسم المادة لا يمكن أن يكون فارغاً.")
                return
                
            new_subject = Subject(
                name=subject_name,
                level_id=STATE[uid]["level"]
            )
            s.add(new_subject)
            s.commit()
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة قسم", callback_data=f"m_sub:{new_subject.id}")],
                [InlineKeyboardButton("🏠 لوحة الإدارة", callback_data="back_admin")]
            ])
            await update.message.reply_text(f"✅ تم إضافة المادة: {new_subject.name}", reply_markup=kb)
            del STATE[uid]
            
        elif step == "section": 
            section_name = update.message.text.strip()
            if not section_name:
                await update.message.reply_text("⚠️ اسم القسم لا يمكن أن يكون فارغاً.")
                return
                
            new_section = Section(
                name=section_name,
                subject_id=STATE[uid]["subject"]
            )
            s.add(new_section)
            s.commit()
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة عنصر", callback_data=f"m_sec:{new_section.id}")],
                [InlineKeyboardButton("🏠 لوحة الإدارة", callback_data="back_admin")]
            ])
            await update.message.reply_text(f"✅ تم إضافة القسم: {new_section.name}", reply_markup=kb)
            del STATE[uid]
            
        elif step == "item": 
            item_name = update.message.text.strip()
            if not item_name:
                await update.message.reply_text("⚠️ اسم العنصر لا يمكن أن يكون فارغاً.")
                return
                
            new_item = Item(
                name=item_name,
                section_id=STATE[uid]["section"]
            )
            s.add(new_item)
            s.commit()
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة محتوى", callback_data=f"m_item:{new_item.id}")],
                [InlineKeyboardButton("🏠 لوحة الإدارة", callback_data="back_admin")]
            ])
            await update.message.reply_text(f"✅ تم إضافة العنصر: {new_item.name}", reply_markup=kb)
            del STATE[uid]
            
        elif step == "content":
            if update.message.photo: 
                val = update.message.photo[-1].file_id
                typ = "file"
            elif update.message.document: 
                val = update.message.document.file_id
                typ = "file"
            elif update.message.video: 
                val = update.message.video.file_id
                typ = "file"
            else: 
                content_text = update.message.text.strip()
                if not content_text:
                    await update.message.reply_text("⚠️ المحتوى لا يمكن أن يكون فارغاً.")
                    return
                val = content_text
                typ = "text"
            
            new_content = Content(
                type=typ,
                value=val,
                item_id=STATE[uid]["item"]
            )
            s.add(new_content)
            s.commit()
            await update.message.reply_text("✅ تم حفظ المحتوى بنجاح")
            del STATE[uid]
            
    except Exception as e:
        logger.error(f"Error in messages: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء المعالجة.")
    finally:
        s.close()

# ================== تشغيل البوت ==================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, messages))
    print("🚀 البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
