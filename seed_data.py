"""
Script de seed de dados para a aplicação Prime Coaching.

Uso:
    python manage.py shell < seed_data.py

Cria:
    - 1 coach (coach / coach123)
    - 5 clientes (cliente1..cliente5 / cliente123)
    - 20 exercícios + grupos musculares
    - 2 planos de treino (com dias e exercícios)
    - 50 alimentos
    - 2 planos alimentares (com refeições e itens)
    - 3 pacotes comerciais
    - Atribuição de pacotes aos clientes
    - 14 dias de histórico de treino e nutrição
"""

import random
from datetime import date, timedelta
from decimal import Decimal

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')  # ajuste se necessário
django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import ClientProfile
from apps.workouts.models import (
    MuscleGroup, Exercise, WorkoutPlan, WorkoutDay,
    WorkoutExercise, WorkoutLog, ExerciseLog,
)
from apps.nutrition.models import (
    FoodItem, NutritionPlan, Meal, MealItem, NutritionLog,
)
from apps.packages.models import CoachingPackage, ClientPackage

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg):
    print(f"  → {msg}")


# ---------------------------------------------------------------------------
# 1. Coach + clientes
# ---------------------------------------------------------------------------

@transaction.atomic
def create_users():
    print("\n[1/7] Criando utilizadores...")

    coach, created = User.objects.get_or_create(
        username="coach",
        defaults={
            "email": "coach@prime.com",
            "first_name": "Ana",
            "last_name": "Silva",
            "role": User.Role.COACH,
            "phone": "+351 912 345 678",
            "bio": "Personal trainer certificada com 10+ anos de experiência.",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    if created:
        coach.set_password("coach123")
        coach.save()
        log(f"Coach criado: {coach.username} / coach123")
    else:
        log(f"Coach já existe: {coach.username}")

    clients = []
    client_data = [
        ("cliente1", "João",   "Pereira", 175, 78,  "Hipertrofia"),
        ("cliente2", "Maria",  "Santos",  165, 62,  "Emagrecimento"),
        ("cliente3", "Pedro",  "Costa",   180, 92,  "Definição"),
        ("cliente4", "Sofia",  "Martins", 170, 58,  "Tonificação"),
        ("cliente5", "Rui",    "Almeida", 178, 85,  "Performance"),
    ]
    for username, first, last, h, w, goal in client_data:
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@prime.com",
                "first_name": first,
                "last_name": last,
                "role": User.Role.CLIENT,
                "coach": coach,
            },
        )
        if created:
            user.set_password("cliente123")
            user.save()
        ClientProfile.objects.update_or_create(
            user=user,
            defaults={
                "height_cm": h,
                "weight_kg": w,
                "goal": goal,
                "notes": f"Cliente focado em {goal.lower()}.",
            },
        )
        clients.append(user)
        log(f"Cliente: {username} / cliente123 ({goal})")

    return coach, clients


# ---------------------------------------------------------------------------
# 2. Exercícios
# ---------------------------------------------------------------------------

@transaction.atomic
def create_exercises(coach):
    print("\n[2/7] Criando exercícios...")

    groups = {}
    for name, icon in [
        ("Peito", "chest"), ("Costas", "back"), ("Pernas", "legs"),
        ("Ombros", "shoulders"), ("Bíceps", "bicep"), ("Tríceps", "tricep"),
        ("Abdômen", "abs"), ("Glúteos", "glutes"),
    ]:
        mg, _ = MuscleGroup.objects.get_or_create(name=name, defaults={"icon": icon})
        groups[name] = mg

    exercises_data = [
        ("Supino Reto",          ["Peito", "Tríceps"], "https://www.youtube.com/embed/rT7DgCr-3pg"),
        ("Supino Inclinado",     ["Peito", "Ombros"],  "https://www.youtube.com/embed/8iPEnn-ltC8"),
        ("Crucifixo",            ["Peito"],            "https://www.youtube.com/embed/eozdVDA78K0"),
        ("Puxada Frente",        ["Costas", "Bíceps"], "https://www.youtube.com/embed/CAwf7n6Luuc"),
        ("Remada Curvada",       ["Costas"],           "https://www.youtube.com/embed/kBWAon7ItDw"),
        ("Remada Unilateral",    ["Costas"],           "https://www.youtube.com/embed/pYcpY20QaE8"),
        ("Agachamento Livre",    ["Pernas", "Glúteos"], "https://www.youtube.com/embed/ultWZbUMPL8"),
        ("Leg Press",            ["Pernas"],           "https://www.youtube.com/embed/IZxyjW7MPJQ"),
        ("Cadeira Extensora",    ["Pernas"],           "https://www.youtube.com/embed/YyvSfVjQeL0"),
        ("Mesa Flexora",         ["Pernas"],           "https://www.youtube.com/embed/1Tq3QdYUuHs"),
        ("Stiff",                ["Pernas", "Glúteos"], "https://www.youtube.com/embed/CN_7cz3P-1U"),
        ("Desenvolvimento",      ["Ombros"],           "https://www.youtube.com/embed/qEwKCR5JCog"),
        ("Elevação Lateral",     ["Ombros"],           "https://www.youtube.com/embed/3VcKaXpzqRo"),
        ("Rosca Direta",         ["Bíceps"],           "https://www.youtube.com/embed/ykJmrZ5v0Oo"),
        ("Rosca Martelo",        ["Bíceps"],           "https://www.youtube.com/embed/zC3nLlEvin4"),
        ("Tríceps Pulley",       ["Tríceps"],          "https://www.youtube.com/embed/2-LAMcpzODU"),
        ("Tríceps Francês",      ["Tríceps"],          "https://www.youtube.com/embed/_gsUck-7M74"),
        ("Abdominal Crunch",     ["Abdômen"],          "https://www.youtube.com/embed/Xyd_fa5zoEU"),
        ("Prancha",              ["Abdômen"],          "https://www.youtube.com/embed/pSHjTRCQxIw"),
        ("Hip Thrust",           ["Glúteos"],          "https://www.youtube.com/embed/SEdqd1n0cvg"),
    ]

    exercises = {}
    for name, mgs, video_url in exercises_data:
        ex, _ = Exercise.objects.get_or_create(
            name=name,
            defaults={
                "description": f"Exercício de {', '.join(mgs).lower()}.",
                "video_url": video_url,
                "instructions": "Mantenha a postura correta e controle o movimento.",
                "created_by": coach,
            },
        )
        ex.muscle_groups.set([groups[m] for m in mgs])
        exercises[name] = ex

    log(f"{len(exercises)} exercícios criados.")
    return exercises


# ---------------------------------------------------------------------------
# 3. Planos de treino
# ---------------------------------------------------------------------------

@transaction.atomic
def create_workout_plans(coach, exercises):
    print("\n[3/7] Criando planos de treino...")

    # Plano ABC
    abc, _ = WorkoutPlan.objects.get_or_create(
        name="Hipertrofia ABC",
        coach=coach,
        defaults={
            "description": "Divisão A (Peito/Tríceps), B (Costas/Bíceps), C (Pernas/Ombros).",
            "duration_weeks": 8,
        },
    )
    abc.days.all().delete()

    days_abc = [
        ("Treino A - Peito/Tríceps", WorkoutDay.DayOfWeek.MONDAY, [
            ("Supino Reto", 4, "8-10", 90),
            ("Supino Inclinado", 4, "10-12", 75),
            ("Crucifixo", 3, "12", 60),
            ("Tríceps Pulley", 4, "12-15", 60),
            ("Tríceps Francês", 3, "10-12", 60),
        ]),
        ("Treino B - Costas/Bíceps", WorkoutDay.DayOfWeek.WEDNESDAY, [
            ("Puxada Frente", 4, "10", 90),
            ("Remada Curvada", 4, "8-10", 90),
            ("Remada Unilateral", 3, "12", 60),
            ("Rosca Direta", 4, "10-12", 60),
            ("Rosca Martelo", 3, "12", 60),
        ]),
        ("Treino C - Pernas/Ombros", WorkoutDay.DayOfWeek.FRIDAY, [
            ("Agachamento Livre", 4, "8-10", 120),
            ("Leg Press", 4, "12", 90),
            ("Cadeira Extensora", 3, "15", 60),
            ("Stiff", 3, "10-12", 90),
            ("Desenvolvimento", 4, "10", 75),
            ("Elevação Lateral", 3, "12-15", 45),
        ]),
    ]
    for order, (name, dow, exs) in enumerate(days_abc):
        day = WorkoutDay.objects.create(plan=abc, name=name, day_of_week=dow, order=order)
        for i, (ex_name, sets, reps, rest) in enumerate(exs):
            WorkoutExercise.objects.create(
                workout_day=day, exercise=exercises[ex_name],
                order=i, sets=sets, reps=reps, rest_seconds=rest,
            )

    # Plano Full Body
    fb, _ = WorkoutPlan.objects.get_or_create(
        name="Full Body Iniciante",
        coach=coach,
        defaults={
            "description": "Treino completo 3x/semana para iniciantes.",
            "duration_weeks": 6,
        },
    )
    fb.days.all().delete()
    fb_exs = [
        ("Agachamento Livre", 3, "12", 90),
        ("Supino Reto", 3, "10", 75),
        ("Puxada Frente", 3, "10", 75),
        ("Desenvolvimento", 3, "12", 60),
        ("Prancha", 3, "30s", 45),
    ]
    for order, dow in enumerate([
        WorkoutDay.DayOfWeek.MONDAY,
        WorkoutDay.DayOfWeek.WEDNESDAY,
        WorkoutDay.DayOfWeek.FRIDAY,
    ]):
        day = WorkoutDay.objects.create(
            plan=fb, name=f"Full Body {chr(65+order)}", day_of_week=dow, order=order,
        )
        for i, (ex_name, sets, reps, rest) in enumerate(fb_exs):
            WorkoutExercise.objects.create(
                workout_day=day, exercise=exercises[ex_name],
                order=i, sets=sets, reps=reps, rest_seconds=rest,
            )

    log(f"2 planos criados: {abc.name}, {fb.name}")
    return [abc, fb]


# ---------------------------------------------------------------------------
# 4. Alimentos + planos alimentares
# ---------------------------------------------------------------------------

@transaction.atomic
def create_nutrition(coach):
    print("\n[4/7] Criando alimentos e planos alimentares...")

    # FoodItem: (name, kcal, P, C, G) por 100g
    foods_data = [
        ("Frango grelhado",     165, 31, 0,    3.6,  "Proteína"),
        ("Carne bovina magra",  217, 26, 0,    11.8, "Proteína"),
        ("Atum em água",        116, 26, 0,    1.0,  "Proteína"),
        ("Salmão",              208, 20, 0,    13.0, "Proteína"),
        ("Ovo inteiro",         155, 13, 1.1,  11.0, "Proteína"),
        ("Whey protein",        400, 80, 8,    5,    "Suplemento"),
        ("Arroz branco cozido", 130, 2.7, 28,  0.3,  "Carboidrato"),
        ("Arroz integral",      111, 2.6, 23,  0.9,  "Carboidrato"),
        ("Batata doce",         86,  1.6, 20,  0.1,  "Carboidrato"),
        ("Aveia",               389, 17, 66,   7,    "Carboidrato"),
        ("Pão integral",        247, 13, 41,   3.5,  "Carboidrato"),
        ("Banana",              89,  1.1, 23,  0.3,  "Fruta"),
        ("Maçã",                52,  0.3, 14,  0.2,  "Fruta"),
        ("Brócolis",            34,  2.8, 7,   0.4,  "Vegetal"),
        ("Salada verde",        15,  1.4, 2.9, 0.2,  "Vegetal"),
        ("Azeite de oliva",     884, 0,   0,   100,  "Gordura"),
        ("Castanha do Pará",    656, 14,  12,  66,   "Gordura"),
        ("Abacate",             160, 2,   9,   15,   "Gordura"),
        ("Iogurte natural",     59,  10,  3.6, 0.4,  "Laticínio"),
        ("Leite desnatado",     34,  3.4, 5,   0.1,  "Laticínio"),
    ]
    foods = {}
    for name, kcal, p, c, g, cat in foods_data:
        f, _ = FoodItem.objects.get_or_create(
            name=name,
            defaults={
                "calories_per_100g": kcal,
                "protein_per_100g": p,
                "carbs_per_100g": c,
                "fat_per_100g": g,
                "category": cat,
            },
        )
        foods[name] = f

    # Plano Bulking
    bulk, _ = NutritionPlan.objects.get_or_create(
        name="Bulking 3000 kcal",
        coach=coach,
        defaults={
            "description": "Plano hipercalórico para ganho de massa.",
            "target_calories": 3000,
            "target_protein": 180,
            "target_carbs": 350,
            "target_fat": 90,
        },
    )
    bulk.meals.all().delete()
    bulk_meals = [
        (Meal.MealType.BREAKFAST, "Café da manhã", "07:00", [
            ("Aveia", 80), ("Banana", 120), ("Whey protein", 30), ("Leite desnatado", 250),
        ]),
        (Meal.MealType.LUNCH, "Almoço", "12:30", [
            ("Frango grelhado", 200), ("Arroz branco cozido", 200), ("Brócolis", 100), ("Azeite de oliva", 10),
        ]),
        (Meal.MealType.AFTERNOON_SNACK, "Lanche", "16:00", [
            ("Pão integral", 80), ("Atum em água", 100), ("Maçã", 150),
        ]),
        (Meal.MealType.DINNER, "Jantar", "20:00", [
            ("Carne bovina magra", 200), ("Batata doce", 250), ("Salada verde", 100),
        ]),
    ]
    for order, (mtype, name, time_str, items) in enumerate(bulk_meals):
        h, m = map(int, time_str.split(":"))
        meal = Meal.objects.create(
            plan=bulk, meal_type=mtype, name=name,
            time=timezone.datetime.min.time().replace(hour=h, minute=m),
            order=order,
        )
        for food_name, grams in items:
            MealItem.objects.create(meal=meal, food=foods[food_name], quantity_grams=grams)

    # Plano Cutting
    cut, _ = NutritionPlan.objects.get_or_create(
        name="Cutting 1800 kcal",
        coach=coach,
        defaults={
            "description": "Plano de déficit calórico para definição.",
            "target_calories": 1800,
            "target_protein": 160,
            "target_carbs": 150,
            "target_fat": 60,
        },
    )
    cut.meals.all().delete()
    cut_meals = [
        (Meal.MealType.BREAKFAST, "Café", "07:30", [
            ("Ovo inteiro", 100), ("Aveia", 40), ("Maçã", 150),
        ]),
        (Meal.MealType.LUNCH, "Almoço", "13:00", [
            ("Frango grelhado", 180), ("Arroz integral", 100), ("Salada verde", 150),
        ]),
        (Meal.MealType.DINNER, "Jantar", "20:00", [
            ("Salmão", 150), ("Brócolis", 200), ("Azeite de oliva", 5),
        ]),
    ]
    for order, (mtype, name, time_str, items) in enumerate(cut_meals):
        h, m = map(int, time_str.split(":"))
        meal = Meal.objects.create(
            plan=cut, meal_type=mtype, name=name,
            time=timezone.datetime.min.time().replace(hour=h, minute=m),
            order=order,
        )
        for food_name, grams in items:
            MealItem.objects.create(meal=meal, food=foods[food_name], quantity_grams=grams)

    log(f"{len(foods)} alimentos e 2 planos alimentares criados.")
    return [bulk, cut]


# ---------------------------------------------------------------------------
# 5. Pacotes
# ---------------------------------------------------------------------------

@transaction.atomic
def create_packages(coach, workout_plans, nutrition_plans, clients):
    print("\n[5/7] Criando pacotes e atribuindo aos clientes...")

    pkgs_data = [
        ("Pack Hipertrofia 30d",  workout_plans[0], nutrition_plans[0], 199.00, 30),
        ("Pack Cutting 60d",      workout_plans[0], nutrition_plans[1], 349.00, 60),
        ("Pack Iniciante 30d",    workout_plans[1], nutrition_plans[1], 149.00, 30),
    ]
    pkgs = []
    for name, wp, np, price, days in pkgs_data:
        p, _ = CoachingPackage.objects.get_or_create(
            name=name, coach=coach,
            defaults={
                "description": f"Pacote {name} com acompanhamento completo.",
                "workout_plan": wp,
                "nutrition_plan": np,
                "price": Decimal(str(price)),
                "duration_days": days,
            },
        )
        pkgs.append(p)

    # Atribuir 1 pacote ativo a cada cliente
    today = date.today()
    for i, client in enumerate(clients):
        pkg = pkgs[i % len(pkgs)]
        ClientPackage.objects.get_or_create(
            client=client, package=pkg,
            defaults={
                "status": ClientPackage.Status.ACTIVE,
                "start_date": today - timedelta(days=14),
                "end_date": today + timedelta(days=pkg.duration_days - 14),
                "assigned_by": coach,
            },
        )

    log(f"{len(pkgs)} pacotes criados e atribuídos.")
    return pkgs


# ---------------------------------------------------------------------------
# 6. Histórico de treino
# ---------------------------------------------------------------------------

@transaction.atomic
def create_workout_history(clients, workout_plans):
    print("\n[6/7] Criando histórico de treinos (14 dias)...")

    today = date.today()
    plan = workout_plans[0]  # ABC
    days = list(plan.days.all())

    total_logs = 0
    for client in clients:
        for offset in range(14, 0, -1):
            d = today - timedelta(days=offset)
            # ~60% de aderência
            if random.random() > 0.6:
                continue
            day = random.choice(days)
            log_obj = WorkoutLog.objects.create(
                client=client, workout_day=day,
                completed=True,
                duration_minutes=random.randint(45, 75),
                notes=random.choice(["Bom treino!", "Cansado hoje", "", "PR no supino", ""]),
            )
            log_obj.date = d
            log_obj.save()

            for we in day.exercises.all():
                base_weight = random.choice([20, 30, 40, 50, 60, 80])
                for s in range(1, we.sets + 1):
                    ExerciseLog.objects.create(
                        workout_log=log_obj,
                        workout_exercise=we,
                        set_number=s,
                        weight_kg=base_weight + random.randint(-5, 10),
                        reps_done=random.randint(8, 12),
                        completed=True,
                    )
            total_logs += 1

    log(f"{total_logs} treinos registrados.")


# ---------------------------------------------------------------------------
# 7. Histórico de nutrição
# ---------------------------------------------------------------------------

@transaction.atomic
def create_nutrition_history(clients, nutrition_plans):
    print("\n[7/7] Criando histórico de nutrição (14 dias)...")

    today = date.today()
    plan = nutrition_plans[0]
    meals = list(plan.meals.all())

    total = 0
    for client in clients:
        for offset in range(14, 0, -1):
            d = today - timedelta(days=offset)
            for meal in meals:
                # ~75% de aderência
                if random.random() > 0.75:
                    continue
                NutritionLog.objects.get_or_create(
                    client=client, date=d, meal=meal,
                    defaults={"completed": True},
                )
                total += 1

    log(f"{total} refeições registradas.")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run():
    print("=" * 60)
    print("  SEED DE DADOS - PRIME COACHING")
    print("=" * 60)

    coach, clients = create_users()
    exercises = create_exercises(coach)
    workout_plans = create_workout_plans(coach, exercises)
    nutrition_plans = create_nutrition(coach)
    create_packages(coach, workout_plans, nutrition_plans, clients)
    create_workout_history(clients, workout_plans)
    create_nutrition_history(clients, nutrition_plans)

    print("\n" + "=" * 60)
    print("  SEED CONCLUÍDO COM SUCESSO!")
    print("=" * 60)
    print("\nCredenciais de acesso:")
    print("  Coach:    coach    / coach123    (admin)")
    print("  Cliente:  cliente1 / cliente123  (e cliente2..cliente5)")
    print()


run()
