"""
Management command: seed_cant_stop_wont_stop

Popula a base de dados com o plano "CAN'T STOP WON'T STOP" (alimentação +
bodyweight) usando os modelos existentes:

    - apps.nutrition: FoodItem, NutritionPlan, Meal, MealItem
    - apps.workouts:  MuscleGroup, Exercise, WorkoutPlan, WorkoutDay, WorkoutExercise
    - apps.coaching:  CoachingPackage (agrega WorkoutPlan + NutritionPlan),
                       ClientPackage (atribuição opcional a um cliente)

Cria DOIS WorkoutPlan / CoachingPackage, ambos para subscrição de 1 mês
(duration_weeks=4, duration_days=30), com o mesmo NutritionPlan associado:

    - "3x/semana (Seg/Qua/Sex)" — Treino A na Segunda, Treino B na Quarta,
      Treino A na Sexta; Terça/Quinta de descanso, Sábado caminhada
      opcional, Domingo descanso.
    - "5x/semana (Seg a Sex)"   — Treino A/B alternados de Segunda a
      Sexta; Sábado caminhada opcional, Domingo descanso.

COMO USAR
---------
1. Copiar este ficheiro para:
       apps/coaching/management/commands/seed_cant_stop_wont_stop.py
       (criar as pastas management/ e management/commands/ com __init__.py
       vazios, se ainda não existirem)

2. Correr:
       python manage.py seed_cant_stop_wont_stop --coach <username_do_coach>

   O utilizador indicado em --coach tem de ter role="coach" (é FK
   obrigatória em Exercise, WorkoutPlan, NutritionPlan e CoachingPackage).

   Opcionalmente, para já atribuir um dos dois pacotes a um cliente (cria
   um ClientPackage), passar também:
       --client <username_do_cliente> --plan 3x --start-date 2026-09-08

   (--plan aceita "3x" ou "5x", por omissão "3x". --start-date é opcional;
   por omissão usa a data de hoje. end_date é calculada automaticamente a
   partir de duration_days=30 do pacote.)

O comando é idempotente: pode ser corrido várias vezes sem duplicar dados
(usa get_or_create em tudo).

NOTA SOBRE OS VALORES NUTRICIONAIS
-----------------------------------
O documento original não trazia calorias/macros — só nomes de alimentos e
porções descritas em linguagem natural ("2 ovos", "1 banana"). Os valores
de FoodItem abaixo são estimativas de referência (por 100 g, alimento
cozido/preparado quando aplicável) e as quantidades em MealItem são
aproximações das porções descritas no plano. Revê/ajusta com um
nutricionista antes de usar como plano clínico real — o próprio documento
tem esse aviso.

NOTA SOBRE Meal / dia da semana
--------------------------------
O modelo Meal não tem campo de "dia da semana" — só meal_type. Para
representar o menu semanal (secção 12 do plano), cada refeição de cada dia
é criada como um Meal separado, com o dia da semana codificado no campo
`name` (ex: "Segunda-feira") e `order` a garantir a sequência correta
(dia * 10 + posição da refeição no dia).
"""

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from apps.workouts.models import (
    MuscleGroup,
    Exercise,
    WorkoutPlan,
    WorkoutDay,
    WorkoutExercise,
)
from apps.nutrition.models import (
    FoodItem,
    NutritionPlan,
    Meal,
    MealItem,
)
from apps.packages.models import (
    CoachingPackage,
    ClientPackage,
)

User = get_user_model()


# =========================================================================
# 1. ALIMENTOS (FoodItem) — valores de referência por 100 g
#    (kcal, proteína g, carboidrato g, gordura g, fibra g, categoria)
# =========================================================================
FOOD_ITEMS = {
    "Ovo cozido":                       (155, 13.0, 1.1, 11.0, 0.0, "Proteína"),
    "Banana":                           (89, 1.1, 23.0, 0.3, 2.6, "Fruta"),
    "Aveia (flocos, cru)":              (389, 16.9, 66.3, 6.9, 10.6, "Cereal"),
    "Pão integral":                     (247, 13.0, 41.0, 4.2, 7.0, "Cereal"),
    "Tomate":                           (18, 0.9, 3.9, 0.2, 1.2, "Vegetal"),
    "Pepino":                           (15, 0.65, 3.6, 0.1, 0.5, "Vegetal"),
    "Batata-doce cozida":               (86, 1.6, 20.1, 0.1, 3.0, "Carboidrato"),
    "Mandioca cozida":                  (160, 1.4, 38.1, 0.3, 1.8, "Carboidrato"),
    "Frango grelhado (peito, s/ pele)": (165, 31.0, 0.0, 3.6, 0.0, "Proteína"),
    "Peixe (tilápia grelhada)":         (128, 26.0, 0.0, 2.7, 0.0, "Proteína"),
    "Carapau grelhado":                 (205, 20.0, 0.0, 13.0, 0.0, "Proteína"),
    "Sardinha":                         (208, 24.6, 0.0, 11.5, 0.0, "Proteína"),
    "Atum em água (enlatado)":          (116, 26.0, 0.0, 0.8, 0.0, "Proteína"),
    "Arroz branco cozido":              (130, 2.7, 28.0, 0.3, 0.4, "Carboidrato"),
    "Xima de milho cozida":             (108, 2.3, 23.0, 0.7, 1.3, "Carboidrato"),
    "Feijão cozido":                    (127, 8.7, 22.8, 0.5, 6.4, "Proteína/Carbo"),
    "Feijão-nhemba cozido":             (116, 7.7, 20.8, 0.5, 6.2, "Proteína/Carbo"),
    "Grão-de-bico cozido":              (164, 8.9, 27.4, 2.6, 7.6, "Proteína/Carbo"),
    "Lentilhas cozidas":                (116, 9.0, 20.0, 0.4, 7.9, "Proteína/Carbo"),
    "Carne bovina magra grelhada":      (187, 26.0, 0.0, 8.6, 0.0, "Proteína"),
    "Laranja":                          (47, 0.9, 11.8, 0.1, 2.4, "Fruta"),
    "Maçã":                             (52, 0.3, 13.8, 0.2, 2.4, "Fruta"),
    "Goiaba":                           (68, 2.6, 14.3, 0.9, 5.4, "Fruta"),
    "Mamão":                            (43, 0.5, 10.8, 0.3, 1.7, "Fruta"),
    "Abacate":                          (160, 2.0, 8.5, 14.7, 6.7, "Fruta"),
    "Iogurte natural sem açúcar":       (61, 3.5, 4.7, 3.3, 0.0, "Laticínio"),
    "Amendoim (sem açúcar)":            (567, 25.8, 16.1, 49.2, 8.5, "Oleaginosa"),
    "Couve cozida":                     (33, 2.9, 6.0, 0.5, 3.6, "Vegetal"),
    "Repolho":                          (25, 1.3, 5.8, 0.1, 2.5, "Vegetal"),
    "Cenoura":                          (41, 0.9, 9.6, 0.2, 2.8, "Vegetal"),
    "Cebola":                           (40, 1.1, 9.3, 0.1, 1.7, "Vegetal"),
    "Abóbora":                          (26, 1.0, 6.5, 0.1, 0.5, "Vegetal"),
    "Matapa (pouco óleo)":              (120, 4.0, 8.0, 8.0, 3.0, "Prato tradicional"),
    "Salada mista (folhas/tomate/pepino)": (20, 1.0, 4.0, 0.2, 1.5, "Vegetal"),
    "Chá sem açúcar":                   (1, 0.0, 0.2, 0.0, 0.0, "Bebida"),
    "Café sem açúcar":                  (2, 0.1, 0.0, 0.0, 0.0, "Bebida"),
}


# =========================================================================
# 2. MENU SEMANAL (secção 12 do plano) — dia, tipo de refeição, itens
#    itens: lista de (nome_do_alimento, quantidade_em_gramas)
# =========================================================================
WEEKLY_MENU = [
    # (dia, ordem_do_dia, meal_type, nome_refeição, itens, notas)
    ("Segunda-feira", 1, "breakfast", "Pequeno-almoço",
     [("Ovo cozido", 100), ("Banana", 120)], "Chá ou café sem açúcar"),
    ("Segunda-feira", 2, "lunch", "Almoço",
     [("Frango grelhado (peito, s/ pele)", 150), ("Xima de milho cozida", 150),
      ("Matapa (pouco óleo)", 100), ("Salada mista (folhas/tomate/pepino)", 100)], ""),
    ("Segunda-feira", 3, "dinner", "Jantar",
     [("Peixe (tilápia grelhada)", 150), ("Salada mista (folhas/tomate/pepino)", 150)], ""),

    ("Terça-feira", 1, "breakfast", "Pequeno-almoço",
     [("Aveia (flocos, cru)", 40), ("Banana", 100), ("Ovo cozido", 50)], ""),
    ("Terça-feira", 2, "lunch", "Almoço",
     [("Peixe (tilápia grelhada)", 150), ("Arroz branco cozido", 150),
      ("Salada mista (folhas/tomate/pepino)", 100)], ""),
    ("Terça-feira", 3, "dinner", "Jantar",
     [("Ovo cozido", 100), ("Batata-doce cozida", 120),
      ("Salada mista (folhas/tomate/pepino)", 100)], ""),

    ("Quarta-feira", 1, "breakfast", "Pequeno-almoço",
     [("Pão integral", 60), ("Ovo cozido", 100)], ""),
    ("Quarta-feira", 2, "lunch", "Almoço",
     [("Feijão cozido", 150), ("Arroz branco cozido", 120), ("Couve cozida", 150)], ""),
    ("Quarta-feira", 3, "dinner", "Jantar",
     [("Frango grelhado (peito, s/ pele)", 150),
      ("Salada mista (folhas/tomate/pepino)", 150)], ""),

    ("Quinta-feira", 1, "breakfast", "Pequeno-almoço",
     [("Batata-doce cozida", 120), ("Ovo cozido", 100)], ""),
    ("Quinta-feira", 2, "lunch", "Almoço",
     [("Carne bovina magra grelhada", 130), ("Xima de milho cozida", 150),
      ("Cenoura", 80), ("Couve cozida", 100)], ""),
    ("Quinta-feira", 3, "dinner", "Jantar",
     [("Peixe (tilápia grelhada)", 150), ("Salada mista (folhas/tomate/pepino)", 150)], ""),

    ("Sexta-feira", 1, "breakfast", "Pequeno-almoço",
     [("Aveia (flocos, cru)", 40), ("Maçã", 120)], ""),
    ("Sexta-feira", 2, "lunch", "Almoço",
     [("Frango grelhado (peito, s/ pele)", 150), ("Arroz branco cozido", 150),
      ("Salada mista (folhas/tomate/pepino)", 100)], ""),
    ("Sexta-feira", 3, "dinner", "Jantar",
     [("Feijão cozido", 150), ("Salada mista (folhas/tomate/pepino)", 150)], ""),

    ("Sábado", 1, "breakfast", "Pequeno-almoço",
     [("Ovo cozido", 100), ("Mamão", 150)], ""),
    ("Sábado", 2, "lunch", "Almoço",
     [("Peixe (tilápia grelhada)", 150), ("Mandioca cozida", 150),
      ("Couve cozida", 100)], ""),
    ("Sábado", 3, "dinner", "Jantar",
     [("Frango grelhado (peito, s/ pele)", 150),
      ("Salada mista (folhas/tomate/pepino)", 150)], ""),

    ("Domingo", 1, "breakfast", "Pequeno-almoço (equilibrado)",
     [("Ovo cozido", 100), ("Banana", 100)], ""),
    ("Domingo", 2, "lunch", "Almoço em família (porção controlada)",
     [("Peixe (tilápia grelhada)", 150), ("Arroz branco cozido", 130),
      ("Salada mista (folhas/tomate/pepino)", 100)], "Refeição livre 20% cabe aqui — regra 80/20"),
    ("Domingo", 3, "dinner", "Jantar leve",
     [("Peixe (tilápia grelhada)", 130), ("Salada mista (folhas/tomate/pepino)", 150)], ""),
]

DAY_NAME_TO_INT = {
    "Segunda-feira": 1,
    "Terça-feira": 2,
    "Quarta-feira": 3,
    "Quinta-feira": 4,
    "Sexta-feira": 5,
    "Sábado": 6,
    "Domingo": 7,
}

SNACK_OPTIONS_NOTE = (
    "Lanche opcional - só se houver fome real ou intervalo longo entre "
    "refeições: banana, maçã, laranja, goiaba, mamão, ovo cozido, iogurte "
    "natural sem açúcar ou pequena porção de amendoim sem açúcar."
)


# =========================================================================
# 3. EXERCÍCIOS BODYWEIGHT (secção 10 do plano)
# =========================================================================
MUSCLE_GROUPS = ["Pernas", "Glúteos", "Peito", "Core", "Cardio", "Corpo Inteiro"]

EXERCISES = {
    # nome: (grupos_musculares, instruções)
    "Agachamento": (["Pernas", "Glúteos"],
        "Pés à largura dos ombros, descer como se fosses sentar, "
        "joelhos alinhados com os pés, subir controlando o movimento."),
    "Flexão de braço": (["Peito", "Corpo Inteiro"],
        "Mãos um pouco mais largas que os ombros, corpo alinhado, "
        "descer o peito até perto do chão e subir."),
    "Flexão inclinada": (["Peito", "Corpo Inteiro"],
        "Mãos apoiadas numa superfície elevada (banco, sofá, degrau) "
        "para reduzir a carga, mesma execução da flexão normal."),
    "Afundo": (["Pernas", "Glúteos"],
        "Dar um passo à frente, descer o joelho de trás quase até o "
        "chão, voltar à posição inicial e alternar a perna."),
    "Mountain climbers": (["Core", "Cardio"],
        "Posição de prancha, trazer os joelhos ao peito alternadamente "
        "num ritmo rápido, mantendo o tronco estável."),
    "Prancha": (["Core"],
        "Apoio em antebraços e pontas dos pés, corpo em linha reta, "
        "abdómen contraído, manter a posição pelo tempo indicado."),
    "Ponte de glúteos": (["Glúteos", "Pernas"],
        "Deitado de costas, joelhos dobrados, elevar a bacia contraindo "
        "os glúteos e descer controladamente."),
    "Abdominal": (["Core"],
        "Deitado de costas, joelhos dobrados, elevar o tronco em "
        "direção aos joelhos contraindo o abdómen."),
    "Burpee": (["Corpo Inteiro", "Cardio"],
        "De pé, agachar, apoiar as mãos no chão, saltar os pés para "
        "trás, fazer uma flexão (opcional), voltar e saltar para cima."),
    "Caminhada / corrida leve": (["Cardio"],
        "Ritmo confortável, conversável, 20-40 minutos, foco em "
        "consistência e recuperação ativa."),
}

# TREINO A / TREINO B — (exercicio, sets, reps, descanso_seg, notas)
TREINO_A = [
    ("Agachamento", 3, "15", 45, "3-4 voltas (circuito)"),
    ("Flexão de braço", 3, "8-15", 45, "3-4 voltas (circuito)"),
    ("Afundo", 3, "10/perna", 45, "3-4 voltas (circuito)"),
    ("Mountain climbers", 3, "20", 30, "3-4 voltas (circuito)"),
    ("Prancha", 3, "30s", 30, "3-4 voltas (circuito)"),
]
TREINO_B = [
    ("Agachamento", 3, "20", 45, "3-4 voltas (circuito)"),
    ("Flexão inclinada", 3, "12", 45, "3-4 voltas (circuito)"),
    ("Ponte de glúteos", 3, "15", 30, "3-4 voltas (circuito)"),
    ("Abdominal", 3, "15", 30, "3-4 voltas (circuito)"),
    ("Burpee", 3, "8-10", 45, "3-4 voltas (circuito)"),
    ("Prancha", 3, "30-45s", 30, "3-4 voltas (circuito)"),
]

# Duas variantes de plano, ambas para uma subscrição de 1 mês (4 semanas):
#   - 3x/semana: Segunda / Quarta / Sexta
#   - 5x/semana: Segunda a Sexta
# dia_da_semana -> (nome_do_dia, treino_ou_None, notas)
WEEK_SCHEDULE_3X = [
    (1, "Treino A", TREINO_A, ""),
    (2, "Descanso", None, "Descanso - sem treino entre os dias de Treino A e B"),
    (3, "Treino B", TREINO_B, ""),
    (4, "Descanso", None, "Descanso - sem treino entre os dias de Treino A e B"),
    (5, "Treino A", TREINO_A, ""),
    (6, "Caminhada / Corrida leve", None, "Opcional - ritmo leve, recuperação ativa"),
    (7, "Descanso", None, "Descanso completo — recuperação"),
]

WEEK_SCHEDULE_5X = [
    (1, "Treino A", TREINO_A, ""),
    (2, "Treino B", TREINO_B, ""),
    (3, "Treino A", TREINO_A, ""),
    (4, "Treino B", TREINO_B, ""),
    (5, "Treino A", TREINO_A, ""),
    (6, "Caminhada / Corrida leve", None, "Opcional - ritmo leve, recuperação ativa"),
    (7, "Descanso", None, "Descanso completo — recuperação"),
]


class Command(BaseCommand):
    help = "Semeia o plano nutricional e bodyweight 'Cant Stop Wont Stop'."

    def add_arguments(self, parser):
        parser.add_argument(
            "--coach",
            required=True,
            help="Username do utilizador coach (role='coach') dono dos planos.",
        )
        parser.add_argument(
            "--client",
            default=None,
            help="Username do cliente (role='client') a quem atribuir o "
                 "pacote via ClientPackage. Opcional.",
        )
        parser.add_argument(
            "--start-date",
            default=None,
            help="Data de início (YYYY-MM-DD) do ClientPackage, se --client "
                 "for indicado. Por omissão, hoje.",
        )
        parser.add_argument(
            "--plan",
            choices=["3x", "5x"],
            default="3x",
            help="Qual dos dois pacotes (3x ou 5x/semana) atribuir ao "
                 "--client, se indicado. Por omissão, '3x'.",
        )

    def handle(self, *args, **options):
        try:
            coach = User.objects.get(username=options["coach"])
        except User.DoesNotExist:
            raise CommandError(f"Utilizador '{options['coach']}' não encontrado.")

        client = None
        if options["client"]:
            try:
                client = User.objects.get(username=options["client"])
            except User.DoesNotExist:
                raise CommandError(f"Cliente '{options['client']}' não encontrado.")

        self.stdout.write("A criar alimentos (FoodItem)...")
        foods = self._seed_food_items()

        self.stdout.write("A criar plano alimentar (NutritionPlan)...")
        nutrition_plan = self._seed_nutrition_plan(coach, foods)

        self.stdout.write("A criar grupos musculares e exercícios...")
        muscle_groups = self._seed_muscle_groups()
        exercises = self._seed_exercises(coach, muscle_groups)

        self.stdout.write("A criar planos de treino bodyweight (WorkoutPlan)...")
        workout_plan_3x = self._seed_workout_plan(
            coach, exercises,
            name="Bodyweight 3x/semana (Seg/Qua/Sex)",
            description=(
                "Programa bodyweight 3x/semana (Segunda, Quarta, Sexta), "
                "sem necessidade de ginásio. Ideal para quem tem menos "
                "disponibilidade de tempo."
            ),
            schedule=WEEK_SCHEDULE_3X,
        )
        workout_plan_5x = self._seed_workout_plan(
            coach, exercises,
            name="Bodyweight 5x/semana (Seg a Sex)",
            description=(
                "Programa bodyweight 5x/semana (Segunda a Sexta, "
                "alternando Treino A/B), sem necessidade de ginásio. "
                "Ideal para quem quer ritmo mais intenso."
            ),
            schedule=WEEK_SCHEDULE_5X,
        )

        self.stdout.write("A criar pacotes de coaching (CoachingPackage, 1 mês)...")
        package_3x = self._seed_coaching_package(
            coach, workout_plan_3x, nutrition_plan,
            name="Cant Stop Wont Stop - 3x/semana (1 mês)",
            description=(
                "Subscrição mensal: plano alimentar (menu semanal) + "
                "treino bodyweight 3x/semana (Seg/Qua/Sex)."
            ),
        )
        package_5x = self._seed_coaching_package(
            coach, workout_plan_5x, nutrition_plan,
            name="Cant Stop Wont Stop - 5x/semana (1 mês)",
            description=(
                "Subscrição mensal: plano alimentar (menu semanal) + "
                "treino bodyweight 5x/semana (Segunda a Sexta)."
            ),
        )

        if client:
            package = package_3x if options["plan"] == "3x" else package_5x
            self.stdout.write(
                f"A atribuir o pacote '{package.name}' ao cliente '{client}'..."
            )
            self._seed_client_package(coach, client, package, options["start_date"])

        self.stdout.write(self.style.SUCCESS(
            "Plano 'Cant Stop Wont Stop' semeado com sucesso."
        ))

    # ------------------------------------------------------------------
    def _seed_food_items(self):
        foods = {}
        for name, (kcal, protein, carbs, fat, fiber, category) in FOOD_ITEMS.items():
            obj, _ = FoodItem.objects.get_or_create(
                name=name,
                defaults=dict(
                    calories_per_100g=kcal,
                    protein_per_100g=protein,
                    carbs_per_100g=carbs,
                    fat_per_100g=fat,
                    fiber_per_100g=fiber,
                    category=category,
                ),
            )
            foods[name] = obj
        return foods

    def _seed_nutrition_plan(self, coach, foods):
        plan, _ = NutritionPlan.objects.get_or_create(
            name="Emagrecimento, condicionamento",
            coach=coach,
            defaults=dict(
                description=(
                    "Plano alimentar geral com alimentos acessíveis em "
                    "Moçambique, baseado na regra do prato (½ vegetais, "
                    "¼ proteína, ¼ carboidrato) e na regra 80/20. Guia "
                    "educativo — não substitui avaliação nutricional "
                    "individual."
                ),
                is_active=True,
            ),
        )

        for day, day_order, meal_type, meal_name, items, notes in WEEKLY_MENU:
            meal, _ = Meal.objects.get_or_create(
                plan=plan,
                day_of_week=DAY_NAME_TO_INT[day],
                meal_type=meal_type,
                defaults=dict(
                    name=f"{day} — {meal_name}",
                    order=day_order + (["breakfast", "lunch", "dinner"].index(meal_type) * 10),
                    notes=notes,
                ),
            )
            for food_name, grams in items:
                MealItem.objects.get_or_create(
                    meal=meal,
                    food=foods[food_name],
                    defaults=dict(quantity_grams=grams),
                )

        # Refeição "coringa" só com a nota sobre lanches (sem itens fixos,
        # já que o plano deixa a escolha em aberto).
        Meal.objects.get_or_create(
            plan=plan,
            name="Lanche (opcional, qualquer dia)",
            meal_type="morning_snack",
            defaults=dict(order=999, notes=SNACK_OPTIONS_NOTE),
        )
        return plan

    # ------------------------------------------------------------------
    def _seed_muscle_groups(self):
        groups = {}
        for name in MUSCLE_GROUPS:
            obj, _ = MuscleGroup.objects.get_or_create(name=name)
            groups[name] = obj
        return groups

    def _seed_exercises(self, coach, muscle_groups):
        exercises = {}
        for name, (group_names, instructions) in EXERCISES.items():
            obj, _ = Exercise.objects.get_or_create(
                name=name,
                created_by=coach,
                defaults=dict(instructions=instructions),
            )
            obj.muscle_groups.set([muscle_groups[g] for g in group_names])
            exercises[name] = obj
        return exercises

    def _seed_workout_plan(self, coach, exercises, name, description, schedule):
        plan, _ = WorkoutPlan.objects.get_or_create(
            name=name,
            coach=coach,
            defaults=dict(
                description=description,
                duration_weeks=4,  # subscrição de 1 mês
                is_active=True,
            ),
        )

        for day_of_week, day_name, treino, notes in schedule:
            workout_day, _ = WorkoutDay.objects.get_or_create(
                plan=plan,
                day_of_week=day_of_week,
                defaults=dict(name=day_name, order=day_of_week, notes=notes),
            )

            if treino:
                for order, (ex_name, sets, reps, rest, ex_notes) in enumerate(treino, start=1):
                    WorkoutExercise.objects.get_or_create(
                        workout_day=workout_day,
                        exercise=exercises[ex_name],
                        defaults=dict(
                            order=order,
                            sets=sets,
                            reps=reps,
                            rest_seconds=rest,
                            notes=ex_notes,
                        ),
                    )
            elif "Caminhada" in day_name:
                WorkoutExercise.objects.get_or_create(
                    workout_day=workout_day,
                    exercise=exercises["Caminhada / corrida leve"],
                    defaults=dict(
                        order=1,
                        sets=1,
                        reps="20-40 min",
                        rest_seconds=0,
                        notes=notes,
                    ),
                )
        return plan

    # ------------------------------------------------------------------
    def _seed_coaching_package(self, coach, workout_plan, nutrition_plan, name, description):
        """
        Agrega o WorkoutPlan + NutritionPlan num CoachingPackage.
        `price` fica em branco (None) — o guia não define preço; ajusta
        depois via admin/painel conforme a tua tabela de preços.
        """
        package, _ = CoachingPackage.objects.get_or_create(
            name=name,
            coach=coach,
            defaults=dict(
                description=description,
                workout_plan=workout_plan,
                nutrition_plan=nutrition_plan,
                duration_days=30,  # subscrição de 1 mês
                is_active=True,
            ),
        )
        return package

    def _seed_client_package(self, coach, client, package, start_date_str):
        if start_date_str:
            start_date = datetime.date.fromisoformat(start_date_str)
        else:
            start_date = datetime.date.today()
        end_date = start_date + datetime.timedelta(days=package.duration_days)

        ClientPackage.objects.get_or_create(
            client=client,
            package=package,
            defaults=dict(
                status=ClientPackage.Status.ACTIVE,
                start_date=start_date,
                end_date=end_date,
                assigned_by=coach,
            ),
        )