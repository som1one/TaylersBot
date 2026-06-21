#!/usr/bin/env python3
"""
Быстрое создание ссылок на оплату ЮKassa
"""

import os
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv('local.env')

def create_payment_link(amount: float, description: str = "Оплата услуги"):
    """Создает ссылку на оплату"""
    try:
        from services.payment_service import PaymentService
        from database.connection import SessionLocal
        from database.models import Tariff
        
        # Создаем временный тариф для платежа
        db = SessionLocal()
        tariff_id = None
        try:
            # Ищем или создаем временный тариф
            temp_tariff = db.query(Tariff).filter(
                Tariff.name == "Временный тариф",
                Tariff.price == amount
            ).first()
            
            if not temp_tariff:
                temp_tariff = Tariff(
                    name="Временный тариф",
                    description=description,
                    price=amount,
                    duration_days=30,
                    is_active=True
                )
                db.add(temp_tariff)
                db.commit()
                print(f"✅ Создан временный тариф на {amount}₽")
            else:
                print(f"✅ Используем существующий тариф на {amount}₽")
            
            # Сохраняем ID тарифа до закрытия сессии
            tariff_id = temp_tariff.id
                
        except Exception as e:
            print(f"❌ Ошибка создания тарифа: {e}")
            db.rollback()
            return None
        finally:
            db.close()
        
        # Создаем платеж
        payment_service = PaymentService()
        result = payment_service.create_payment(
            user_id=999999999,  # Временный пользователь
            tariff_id=tariff_id,
            amount=amount,
            description=description
        )
        
        return result
        
    except Exception as e:
        print(f"❌ Ошибка создания платежа: {e}")
        return None

def main():
    """Основная функция"""
    print("💳 Создание ссылки на оплату ЮKassa")
    print("=" * 50)
    
    # Проверяем конфигурацию
    shop_id = os.getenv('YOOKASSA_SHOP_ID')
    secret_key = os.getenv('YOOKASSA_SECRET_KEY')
    
    if not shop_id or not secret_key:
        print("❌ Не настроены ключи ЮKassa в local.env")
        return
    
    print(f"✅ Shop ID: {shop_id}")
    print(f"✅ Secret Key: {secret_key[:10]}...")
    
    # Запрашиваем сумму
    try:
        amount = float(input("\n💰 Введите сумму платежа (в рублях): "))
        if amount <= 0:
            print("❌ Сумма должна быть больше 0")
            return
    except ValueError:
        print("❌ Неверный формат суммы")
        return
    
    # Запрашиваем описание
    description = input("📝 Введите описание платежа (или нажмите Enter для пропуска): ").strip()
    if not description:
        description = f"Оплата на сумму {amount}₽"
    
    print(f"\n🔄 Создаем платеж на {amount}₽...")
    
    # Создаем платеж
    result = create_payment_link(amount, description)
    
    if result:
        print("\n" + "=" * 50)
        print("✅ Платеж успешно создан!")
        print(f"📋 Payment ID: {result['payment_id']}")
        print(f"🔗 Ссылка для оплаты:")
        print(f"   {result['confirmation_url']}")
        print(f"📊 Статус: {result['status']}")
        print(f"💰 Сумма: {result['amount']}₽")
        print(f"📦 Тариф: {result['tariff_name']}")
        
        print("\n📝 Тестовые карты ЮKassa:")
        print("   ✅ 1111 1111 1111 1026 (успешная оплата)")
        print("   ❌ 1111 1111 1111 1051 (недостаточно средств)")
        print("   ❌ 1111 1111 1111 1100 (карта заблокирована)")
    else:
        print("\n❌ Не удалось создать платеж!")

if __name__ == "__main__":
    main()
