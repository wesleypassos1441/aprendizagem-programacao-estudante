import os
import re
import time
import traceback
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


LOGIN_URL = "https://login.anhanguera.com/"
AVA_URL_FRAGMENT = "avaeduc.com.br"
ARTIFACTS_DIR = Path("artifacts")
NON_FUNCTIONAL_UNIT_URLS: set[str] = set()


@dataclass
class Credentials:
    cpf: str
    password: str


@dataclass
class QuizQuestion:
    label: str
    statement: str
    alternatives: list[str]


@dataclass
class UnitLink:
    href: str
    text: str
    source: str
    index: int


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "sim", "s"}


def masked_input(prompt: str, mask: str = "•") -> str:
    print(prompt, end="", flush=True)

    if os.name == "nt":
        import msvcrt

        chars: list[str] = []
        while True:
            char = msvcrt.getwch()
            if char in {"\r", "\n"}:
                print()
                return "".join(chars)
            if char == "\x03":
                raise KeyboardInterrupt
            if char in {"\x00", "\xe0"}:
                msvcrt.getwch()
                continue
            if char in {"\b", "\x7f"}:
                if chars:
                    chars.pop()
                    print("\b \b", end="", flush=True)
                continue
            chars.append(char)
            print(mask, end="", flush=True)

    # Fallback simples para ambientes fora do Windows.
    return input()


def load_credentials() -> Credentials:
    while True:
        cpf = re.sub(r"\D", "", input("Insira seu CPF: ").strip())
        if cpf:
            break
        print("CPF obrigatório. Digite novamente.")

    while True:
        password = masked_input("Insira sua senha: ").strip()
        if password:
            break
        print("Senha obrigatória. Digite novamente.")

    return Credentials(cpf=cpf, password=password)

def configure_session_gemini_api_key() -> None:
    while True:
        session_key = input("Cole a API key Gemini que será usada nesta sessão: ").strip()
        if session_key:
            os.environ["GEMINI_API_KEY"] = session_key
            return
        print("API key obrigatória. Cole uma chave Gemini para continuar.")

def request_new_gemini_api_key() -> bool:
    new_key = input(
        "\nA cota da API atual foi atingida. "
        "Cole outra API key Gemini para continuar, "
        "ou pressione Enter para seguir sem Gemini: "
    ).strip()
    if not new_key:
        return False

    os.environ["GEMINI_API_KEY"] = new_key
    print("Nova API key recebida. Tentando novamente sem reiniciar o fluxo...")
    return True

def first_visible(page: Page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() and locator.first.is_visible():
            return locator.first
    return None


def login_error_visible(page: Page) -> bool:
    error_patterns = [
        r"usu[aá]rio\s+ou\s+senha\s+inv[aá]lid",
        r"cpf\s+ou\s+senha\s+inv[aá]lid",
        r"senha\s+inv[aá]lid",
        r"credenciais?\s+inv[aá]lid",
        r"dados\s+inv[aá]lid",
        r"login\s+inv[aá]lid",
        r"n[aã]o\s+foi\s+poss[ií]vel\s+autenticar",
        r"n[aã]o\s+foi\s+poss[ií]vel\s+realizar\s+o\s+login",
    ]

    try:
        body_text = page.locator("body").inner_text(timeout=2_000)
    except Exception:
        return False

    return any(re.search(pattern, body_text, re.I) for pattern in error_patterns)


def login_page_still_visible(page: Page) -> bool:
    try:
        password_field = page.locator('input[type="password"], [data-testid="password-input"]')
        enter_button = page.get_by_text(re.compile(r"^entrar$", re.I))
        return bool(
            password_field.count()
            and password_field.first.is_visible()
            and enter_button.count()
            and enter_button.first.is_visible()
        )
    except Exception:
        return False


def wait_for_login_result(page: Page) -> bool:
    for attempt in range(1, 31):
        page.wait_for_timeout(1_000)

        if login_error_visible(page):
            return False

        current_url = page.url.lower()
        if "login.anhanguera.com" not in current_url:
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                pass
            return True

        if attempt >= 8 and login_page_still_visible(page):
            return False

    return "login.anhanguera.com" not in page.url.lower()


def perform_login(page: Page, credentials: Credentials) -> bool:
    print("Abrindo login...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PlaywrightTimeoutError:
        pass
    accept_cookies_if_present(page)

    try:
        print("Preenchendo CPF...")
        fill_cpf(page, credentials.cpf)
        click_by_text(page, "Avançar")
        page.wait_for_timeout(1_500)

        if login_error_visible(page):
            return False

        print("Preenchendo senha...")
        fill_password(page, credentials.password)
        click_by_text(page, "Entrar")
        return wait_for_login_result(page)
    except PlaywrightTimeoutError:
        return False


def fill_cpf(page: Page, cpf: str) -> None:
    selectors = [
        '[data-testid="login-input"]',
        '#username',
        'input[name*="cpf" i]',
        'input[id*="cpf" i]',
        'input[placeholder*="cpf" i]',
        'input[type="text"]',
    ]

    page.wait_for_selector(", ".join(selectors), timeout=20_000)

    for attempt in range(1, 6):
        accept_cookies_if_present(page)
        field = first_visible(page, selectors)

        if field is not None:
            field.wait_for(state="visible", timeout=10_000)
            field.click()
            field.fill("")
            field.fill(cpf)
            page.wait_for_timeout(700)

            current_value = field.input_value().strip()
            if current_value == cpf:
                return

        print(f"Aviso: tentativa {attempt} de preencher o CPF não concluiu; tentando novamente...")
        page.wait_for_timeout(1_000)

    raise RuntimeError("Não consegui preencher o campo de CPF após várias tentativas.")


def fill_password(page: Page, password: str) -> None:
    page.wait_for_selector('input[type="password"], [data-testid="password-input"]', timeout=20_000)
    field = first_visible(
        page,
        [
            '[data-testid="password-input"]',
            'input[type="password"]',
            'input[name*="senha" i]',
            'input[id*="senha" i]',
        ],
    )
    if field is None:
        raise RuntimeError("Não encontrei o campo de senha.")
    field.fill(password)


def click_by_text(page: Page, text: str, timeout: int = 15_000) -> None:
    page.get_by_text(re.compile(rf"^{re.escape(text)}\s*$", re.I)).click(timeout=timeout)


def accept_cookies_if_present(page: Page) -> None:
    button = first_visible(
        page,
        [
            "#agreeButton",
            '[data-testid="privacy-bar"] button',
            'button:has-text("OK")',
            'button:has-text("Ok")',
        ],
    )
    if button:
        button.click()


def dismiss_initial_announcement(page: Page) -> None:
    advanced_announcement = False
    try:
        page.get_by_text(re.compile(r"pr[oó]ximo comunicado", re.I)).click(timeout=10_000)
        advanced_announcement = True
    except PlaywrightTimeoutError:
        print("Aviso: não encontrei 'Próximo comunicado'; seguindo.")

    close_selectors = [
        "button.title-dismiss-icons",
        ".announcement-container button.close.fa-times",
        ".announcement-container button[aria-label*='Ignorar comunicado' i]",
        "button.close.fa-times",
        ".modal button.close",
        '[role="dialog"] button.close',
        '[role="dialog"] button[aria-label*="fechar" i]',
        '[role="dialog"] button[title*="fechar" i]',
        '.modal button[aria-label*="fechar" i]',
        '.modal button[title*="fechar" i]',
        '[aria-label*="fechar" i]',
        '[title*="fechar" i]',
        'button:has-text("×")',
        'button:has-text("x")',
    ]

    def announcement_still_open() -> bool:
        indicators = [
            "button.title-dismiss-icons",
            ".announcement-container",
            "body.modal-open",
            ".modal.show",
            ".modal.in",
            '[role="dialog"]',
        ]
        try:
            return any(
                page.locator(selector).count()
                and page.locator(selector).first.is_visible()
                for selector in indicators
            )
        except Exception as error:
            if "Execution context was destroyed" in str(error):
                return False
            raise

    for attempt in range(1, 6):
        try:
            page.wait_for_timeout(1_500)
        except Exception as error:
            if "Execution context was destroyed" in str(error):
                return
            raise

        if not announcement_still_open():
            return

        for selector in close_selectors:
            locator = page.locator(selector)
            for index in range(locator.count()):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible():
                        candidate.scroll_into_view_if_needed()
                        candidate.click(timeout=5_000, force=True)
                        page.wait_for_timeout(1_000)
                        if not announcement_still_open():
                            return
                except Exception:
                    continue

        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(1_000)
            if not announcement_still_open():
                return
        except Exception as error:
            if "Execution context was destroyed" in str(error):
                return

        print(f"Aviso: tentativa {attempt} de fechar o comunicado não concluiu; tentando novamente...")

    if not advanced_announcement:
        print(
            "Aviso: não havia 'Próximo comunicado'; tentei fechar diretamente o comunicado exibido."
        )

    visible_buttons = page.locator("button").evaluate_all(
        """buttons => buttons
            .filter(button => {
                const style = window.getComputedStyle(button);
                const rect = button.getBoundingClientRect();
                return style.visibility !== 'hidden' &&
                       style.display !== 'none' &&
                       rect.width > 0 &&
                       rect.height > 0;
            })
            .map(button => ({
                text: button.innerText,
                aria: button.getAttribute('aria-label'),
                title: button.getAttribute('title'),
                className: button.className
            }))"""
    )
    print("Aviso: não consegui fechar o comunicado automaticamente.")
    print("Botões visíveis encontrados na página:")
    for button in visible_buttons:
        print(button)


def go_to_study_area(page: Page) -> Page:
    context = page.context
    existing_pages = set(context.pages)

    study_targets = [
        'a:has-text("Estudar")',
        'button:has-text("Estudar")',
        '[role="link"]:has-text("Estudar")',
        '[role="button"]:has-text("Estudar")',
        'text=Estudar',
    ]

    clicked = False
    for selector in study_targets:
        locator = page.locator(selector)
        for index in range(locator.count()):
            candidate = locator.nth(index)
            try:
                if candidate.is_visible():
                    candidate.click(timeout=5_000, force=True)
                    clicked = True
                    break
            except Exception:
                continue
        if clicked:
            break

    if not clicked:
        raise RuntimeError("Não encontrei nenhum elemento clicável com o texto 'Estudar'.")

    try:
        new_page = context.wait_for_event("page", timeout=5_000)
        new_page.wait_for_load_state("networkidle")
        return new_page
    except PlaywrightTimeoutError:
        pass

    for candidate in context.pages:
        if candidate not in existing_pages:
            candidate.wait_for_load_state("networkidle")
            return candidate

    page.wait_for_load_state("networkidle")
    return page


def choose_discipline(page: Page, discipline_name: str) -> None:
    discipline_pattern = re.compile(re.escape(discipline_name), re.I)
    matching_text = page.get_by_text(discipline_pattern)

    if not matching_text.count():
        raise RuntimeError(
            f"Não encontrei a disciplina '{discipline_name}' na tela. "
            "Verifique se ela está visível entre as disciplinas carregadas."
        )

    matching_card = matching_text.first.locator(
        'xpath=ancestor::*[.//*[normalize-space()="ACESSAR A DISCIPLINA"]][1]'
    )

    if matching_card.count():
        access_button = matching_card.get_by_text(re.compile(r"^acessar a disciplina$", re.I))
        if access_button.count():
            access_button.first.click(timeout=20_000)
            return

    print(
        f"Aviso: encontrei a disciplina '{discipline_name}', mas não achei o botão dentro do card pelo caminho principal."
    )

    fallback_candidates = [
        matching_text.first.locator(
            'xpath=ancestor::*[self::div or self::section][.//*[contains(translate(normalize-space(), '
            '"abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"), "ACESSAR A DISCIPLINA")]][1]'
        ),
        matching_text.first.locator("xpath=ancestor::*[self::div or self::section][1]"),
    ]

    for candidate_card in fallback_candidates:
        if candidate_card.count():
            buttons = candidate_card.locator(
                'text=/^\\s*acessar\\s+a\\s+disciplina\\s*$/i'
            )
            if buttons.count():
                buttons.first.click(timeout=20_000)
                return

    raise RuntimeError(
        f"Encontrei a disciplina '{discipline_name}', mas não consegui localizar o botão "
        "'ACESSAR A DISCIPLINA' associado a ela."
    )


def list_available_disciplines(page: Page) -> list[str]:
    cards = page.locator(".card-item")
    disciplines: list[str] = []

    for index in range(cards.count()):
        card = cards.nth(index)
        access_button = card.get_by_text(re.compile(r"^acessar a disciplina$", re.I))
        title = card.locator(".card-content-title")

        if access_button.count() and title.count():
            discipline_name = title.first.inner_text().strip()
            if discipline_name and discipline_name not in disciplines:
                disciplines.append(discipline_name)

    if not disciplines:
        raise RuntimeError("Não consegui identificar as disciplinas disponíveis na tela.")

    return disciplines


def ask_user_to_choose_discipline(page: Page) -> str:
    disciplines = list_available_disciplines(page)

    print("\nDisciplinas disponíveis:")
    for index, discipline in enumerate(disciplines, start=1):
        print(f"{index} - {discipline}")

    while True:
        choice = input("Qual disciplina deseja acessar? Digite o número: ").strip()
        if choice.isdigit():
            selected_index = int(choice)
            if 1 <= selected_index <= len(disciplines):
                return disciplines[selected_index - 1]
        print("Opção inválida. Escolha um número da lista.")


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_search_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return compact_text(value).lower()


def activity_key_from_text(text: str) -> str:
    normalized = normalize_search_text(text)
    if "atividade diagnostica" in normalized:
        return "diagnostica"
    if "atividade de aprendiz" in normalized:
        return "atividade de aprendizagem"
    if "avaliacao da unidade" in normalized:
        return "avaliação da unidade"
    return ""


def activity_label_from_key(key: str) -> str:
    for definition_key, label, _ in ACTIVITY_DEFINITIONS:
        if definition_key == key:
            return label
    return key


def get_unit_links(page: Page, unit_choice: str) -> list[UnitLink]:
    normalized_unit = normalize_unit_choice(unit_choice)
    unit_pattern = re.compile(
        rf"\bunidade\s+(?:de\s+ensino\s+)?{normalized_unit}\b",
        re.I,
    )
    exact_unit_pattern = re.compile(
        rf"^unidade\s+(?:de\s+ensino\s+)?{normalized_unit}$",
        re.I,
    )

    selectors = [
        (".timeline-item a", "timeline"),
        ('a[href*="course/view.php"][href*="topic="]', "course-topic"),
        ('a[href*="topic="]', "topic"),
    ]

    links: list[UnitLink] = []
    seen_hrefs: set[str] = set()

    # Modelo accordion: algumas disciplinas (ex.: Engenharia de Software)
    # mostram "Unidade de Ensino X" como grupo expansível e as páginas reais
    # ficam dentro de "UX - Seção 1..4".
    try:
        grouped_sections = page.evaluate(
            """({ unitNumber }) => {
                const normalize = value => (value || '').replace(/\\s+/g, ' ').trim();
                const wanted = new RegExp(`\\\\bunidade\\\\s+(?:de\\\\s+ensino\\\\s+)?${unitNumber}\\\\b`, 'i');
                const groups = Array.from(document.querySelectorAll('.timeline-item.group'));
                const results = [];

                for (const group of groups) {
                    const groupText = normalize([
                        group.getAttribute('data-ct-groupname'),
                        group.innerText,
                        group.textContent,
                    ].filter(Boolean).join(' '));

                    if (!wanted.test(groupText)) continue;

                    let cursor = group.nextElementSibling;
                    while (cursor && !cursor.classList.contains('timeline-menu')) {
                        cursor = cursor.nextElementSibling;
                    }

                    if (!cursor) continue;

                    Array.from(cursor.querySelectorAll('a[href*="topic="]')).forEach((node, index) => {
                        results.push({
                            href: node.href || node.getAttribute('href') || '',
                            text: `${groupText} > ${normalize(node.innerText || node.textContent)}`,
                            source: 'group-section',
                            index,
                        });
                    });
                }

                return results;
            }""",
            {"unitNumber": normalized_unit},
        )
    except Exception:
        grouped_sections = []

    for raw_link in grouped_sections:
        href = compact_text(raw_link.get("href", ""))
        text = compact_text(raw_link.get("text", ""))
        if href and href not in seen_hrefs:
            links.append(
                UnitLink(
                    href=href,
                    text=text,
                    source="group-section",
                    index=int(raw_link.get("index", 0)),
                )
            )
            seen_hrefs.add(href)

    for selector, source in selectors:
        try:
            raw_links = page.evaluate(
                """({ selector, source }) => {
                    const normalize = value => (value || '').replace(/\\s+/g, ' ').trim();
                    return Array.from(document.querySelectorAll(selector)).map((node, index) => ({
                        href: node.href || node.getAttribute('href') || '',
                        text: normalize([
                            node.innerText,
                            node.textContent,
                            node.getAttribute('aria-label'),
                            node.getAttribute('title')
                        ].filter(Boolean).join(' ')),
                        source,
                        index
                    }));
                }""",
                {"selector": selector, "source": source},
            )
        except Exception:
            continue

        for raw_link in raw_links:
            href = compact_text(raw_link.get("href", ""))
            text = compact_text(raw_link.get("text", ""))
            if not href or href == "#" or href.endswith("#") or href in seen_hrefs:
                continue

            if unit_pattern.search(text):
                links.append(
                    UnitLink(
                        href=href,
                        text=text,
                        source=raw_link.get("source", source),
                        index=int(raw_link.get("index", 0)),
                    )
                )
                seen_hrefs.add(href)

    # Se o AVA mudar o HTML de novo, ainda tentamos achar textos clicáveis e
    # subir até o <a> mais próximo. Isso é a rede de segurança.
    if not links:
        fallback_locator = page.get_by_text(exact_unit_pattern)
        for index in range(fallback_locator.count()):
            try:
                anchor = fallback_locator.nth(index).locator("xpath=ancestor-or-self::a[1]")
                href = compact_text(anchor.get_attribute("href") or "")
                text = compact_text(anchor.inner_text())
                if href and href not in seen_hrefs:
                    links.append(UnitLink(href=href, text=text, source="text-fallback", index=index))
                    seen_hrefs.add(href)
            except Exception:
                continue

    source_priority = {
        "group-section": 0,
        "timeline": 0,
        "course-topic": 1,
        "topic": 2,
        "text-fallback": 3,
    }
    links.sort(
        key=lambda link: (
            link.href in NON_FUNCTIONAL_UNIT_URLS,
            source_priority.get(link.source, 99),
            link.index,
        )
    )
    return links


def choose_unit(page: Page, unit_choice: str, occurrence_index: int = 0) -> None:
    normalized_unit = normalize_unit_choice(unit_choice)
    try:
        page.wait_for_selector(
            '.timeline-item a, a[href*="course/view.php"][href*="topic="], a[href*="topic="]',
            timeout=20_000,
        )
    except PlaywrightTimeoutError:
        pass

    visible_matches = get_unit_links(page, unit_choice)

    if occurrence_index < len(visible_matches):
        selected = visible_matches[occurrence_index]
        page.goto(selected.href, wait_until="domcontentloaded")
        return

    available_units = ", ".join(
        f"{match.text} -> {match.href}" for match in visible_matches[:6]
    )
    if not available_units:
        available_units = "nenhuma unidade correspondente detectada no HTML atual"

    raise RuntimeError(
        f"Não encontrei a unidade correspondente a '{unit_choice}'. "
        f"Procurei por 'Unidade de Ensino {normalized_unit}' "
        f"na ocorrência {occurrence_index + 1}. "
        f"Ocorrências disponíveis: {len(visible_matches)}. "
        f"Detectado: {available_units}."
    )


def count_unit_occurrences(page: Page, unit_choice: str) -> int:
    return len(get_unit_links(page, unit_choice))


def open_unit_occurrence(page: Page, unit_choice: str, occurrence_index: int) -> bool:
    try:
        choose_unit(page, unit_choice, occurrence_index=occurrence_index)
        page.wait_for_load_state("networkidle")
        return True
    except Exception as error:
        if "ocorrências disponíveis" in str(error):
            return False
        raise


def unit_is_unavailable(page: Page) -> bool:
    unavailable_pattern = re.compile(
        r"dispon[ií]vel\s+a\s+partir\s+de\s+\d{1,2}\s+\w+\s+\d{4}",
        re.I,
    )
    locator = page.get_by_text(unavailable_pattern)
    return locator.count() > 0


def remember_non_functional_unit(page: Page) -> None:
    current_url = page.url
    if current_url:
        NON_FUNCTIONAL_UNIT_URLS.add(current_url)
        print(f"Memorizando unidade não funcional para evitar nesta sessão: {current_url}")


def normalize_unit_choice(unit_choice: str) -> str:
    match = re.search(r"(\d+)", unit_choice)
    if not match:
        raise RuntimeError(
            "Não consegui identificar o número da unidade. "
            "Exemplos válidos: '1', 'Unidade 1' ou 'Unidade de Ensino 1'."
        )
    return match.group(1)


def extract_section_number(text: str) -> str:
    match = re.search(r"se[cç][aã]o\s*(\d+)", text, re.I)
    return match.group(1) if match else ""


def get_expandable_section_links(page: Page, unit_choice: str) -> list[UnitLink]:
    return [
        link
        for link in get_unit_links(page, unit_choice)
        if link.source == "group-section" and extract_section_number(link.text)
    ]


def ask_unit_choice(page: Page) -> str:
    while True:
        unit_choice = input(
            "Qual unidade deseja acessar? (ou digite 'sair' para encerrar): "
        ).strip()
        if unit_choice.lower() == "sair":
            return "sair"
        if not unit_choice:
            print("Opção inválida. Informe uma unidade antes de continuar.")
            continue

        try:
            normalized_unit = normalize_unit_choice(unit_choice)
        except RuntimeError as error:
            print(f"Opção inválida. {error}")
            continue

        if not get_unit_links(page, unit_choice):
            print(
                f"Opção inválida. Não encontrei 'Unidade de Ensino {normalized_unit}' "
                "nesta matéria. Tente novamente."
            )
            continue

        return unit_choice


def ask_section_choice(section_links: list[UnitLink]) -> UnitLink:
    by_section: dict[str, UnitLink] = {}
    for link in section_links:
        section_number = extract_section_number(link.text)
        if section_number and section_number not in by_section:
            by_section[section_number] = link

    ordered_sections = sorted(by_section, key=lambda value: int(value))
    while True:
        print("\nSeções disponíveis:")
        for section_number in ordered_sections:
            print(f"{section_number} - Seção {section_number}")

        choice = input("Qual seção deseja acessar? Digite o número: ").strip()
        if choice in by_section:
            return by_section[choice]

        print("Opção inválida. Escolha uma seção disponível da lista.")


def ask_activity_choice(options: list[tuple[str, str]]) -> str:
    while True:
        print("\nAtividades disponíveis:")
        for index, (_, label) in enumerate(options, start=1):
            print(f"{index} - {label}")

        choice = input("Qual atividade deseja acessar? Digite o número: ").strip()
        if choice.isdigit():
            selected_index = int(choice)
            if 1 <= selected_index <= len(options):
                return options[selected_index - 1][0]

        print("Opção inválida. Escolha um número da lista.")


ACTIVITY_DEFINITIONS: list[tuple[str, str, re.Pattern]] = [
    ("diagnostica", "Atividade Diagnóstica", re.compile(r"atividade\s+diagn[oó]stica", re.I)),
    (
        "atividade de aprendizagem",
        "Atividade de Aprendizagem",
        re.compile(r"atividade\s+de\s+aprendiz(?:agem|ado)", re.I),
    ),
    ("avaliação da unidade", "Avaliação da Unidade", re.compile(r"avalia[cç][aã]o\s+da\s+unidade", re.I)),
]


def activity_definition_for_choice(activity_choice: str) -> tuple[str, str, re.Pattern]:
    normalized = activity_choice.strip().lower()
    aliases = {
        "1": "atividade de aprendizagem",
        "atividade": "atividade de aprendizagem",
        "atividade de aprendizagem": "atividade de aprendizagem",
        "atividade de aprendizado": "atividade de aprendizagem",
        "aprendizagem": "atividade de aprendizagem",
        "aprendizado": "atividade de aprendizagem",
        "2": "avaliação da unidade",
        "avaliacao": "avaliação da unidade",
        "avaliação": "avaliação da unidade",
        "avaliação da unidade": "avaliação da unidade",
        "3": "diagnostica",
        "diagnostica": "diagnostica",
        "diagnóstica": "diagnostica",
        "atividade diagnostica": "diagnostica",
        "atividade diagnóstica": "diagnostica",
    }
    key = aliases.get(normalized, normalized)

    for definition in ACTIVITY_DEFINITIONS:
        if definition[0] == key:
            return definition

    raise RuntimeError(
        "Opção inválida. Escolha uma atividade disponível da lista apresentada."
    )


FORBIDDEN_ACTIVITY_TARGET_TERMS = (
    "webaula",
    "web aula",
    "video",
    "vídeo",
    "material",
    "livro",
    "manual",
    "lista",
    "forum",
    "fórum",
    "plano de ensino",
)


def is_safe_activity_href(href: str) -> bool:
    normalized_href = normalize_search_text(href)
    return "/mod/quiz/" in normalized_href


def is_forbidden_activity_text(text: str, href: str = "") -> bool:
    normalized = normalize_search_text(f"{text} {href}")
    return any(term in normalized for term in FORBIDDEN_ACTIVITY_TARGET_TERMS)


def collect_activity_targets(page: Page) -> list[dict[str, str]]:
    try:
        raw_targets = page.evaluate(
            r"""() => {
                const normalize = value => (value || '').replace(/\s+/g, ' ').trim();
                const selectors = [
                    'a[href*="/mod/quiz/"]',
                    'a[href*="mod/quiz/"]',
                    '.modtype_quiz',
                    'li.activity.modtype_quiz',
                    '.activityinstance'
                ].join(',');

                return Array.from(document.querySelectorAll(selectors)).map((node, index) => {
                    const link = node.matches('a[href]')
                        ? node
                        : node.querySelector('a[href*="/mod/quiz/"], a[href*="mod/quiz/"]')
                            || node.closest('a[href*="/mod/quiz/"], a[href*="mod/quiz/"]');
                    return {
                        href: link ? (link.href || link.getAttribute('href') || '') : '',
                        text: normalize([
                            node.innerText,
                            node.textContent,
                            node.getAttribute('aria-label'),
                            node.getAttribute('title'),
                            link && link.innerText,
                            link && link.textContent,
                            link && link.getAttribute('aria-label'),
                            link && link.getAttribute('title')
                        ].filter(Boolean).join(' ')),
                        index
                    };
                });
            }"""
        )
    except Exception:
        raw_targets = []

    targets: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for raw_target in raw_targets:
        href = compact_text(raw_target.get("href", ""))
        text = compact_text(raw_target.get("text", ""))
        if not text:
            continue

        key = activity_key_from_text(text)
        if not key:
            continue
        if not href or not is_safe_activity_href(href):
            continue
        if is_forbidden_activity_text(text, href):
            continue

        label = activity_label_from_key(key)
        dedupe_key = (key, href, text[:120])
        if dedupe_key in seen:
            continue

        targets.append(
            {
                "key": key,
                "label": label,
                "href": href,
                "text": text,
            }
        )
        seen.add(dedupe_key)

    return targets


def body_has_activity(page: Page, activity_key: str) -> bool:
    try:
        body_text = page.locator("body").inner_text(timeout=5_000)
    except Exception:
        return False

    normalized = normalize_search_text(body_text)
    if activity_key == "diagnostica":
        return "atividade diagnostica" in normalized
    if activity_key == "atividade de aprendizagem":
        return "atividade de aprendiz" in normalized
    if activity_key == "avaliação da unidade":
        return "avaliacao da unidade" in normalized
    return False


def visible_activity_options(page: Page) -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = []
    seen_keys: set[str] = set()

    for target in collect_activity_targets(page):
        key = target["key"]
        if key in seen_keys:
            continue
        options.append((key, target["label"]))
        seen_keys.add(key)

    # Fallback apenas para exibir opções no terminal. A abertura continua exigindo
    # link seguro de questionário (/mod/quiz/) para nunca cair em Webaula/Material.
    for key, label, pattern in ACTIVITY_DEFINITIONS:
        if key in seen_keys:
            continue
        if body_has_activity(page, key):
            options.append((key, label))
            seen_keys.add(key)

    return options


def classic_activity_options(page: Page) -> list[tuple[str, str]]:
    detected = visible_activity_options(page)
    if detected:
        return detected

    return [(key, label) for key, label, _ in ACTIVITY_DEFINITIONS]


def click_activity_by_dom_text(page: Page, activity_key: str) -> bool:
    try:
        return bool(
            page.evaluate(
                r"""({ activityKey }) => {
                    const normalize = value => (value || '')
                        .normalize('NFD')
                        .replace(/[\u0300-\u036f]/g, '')
                        .replace(/\s+/g, ' ')
                        .trim()
                        .toLowerCase();

                    const matches = text => {
                        const normalized = normalize(text);
                        if (activityKey === 'diagnostica') return normalized.includes('atividade diagnostica');
                        if (activityKey === 'atividade de aprendizagem') return normalized.includes('atividade de aprendiz');
                        if (activityKey === 'avaliação da unidade') return normalized.includes('avaliacao da unidade');
                        return false;
                    };

                    const isSafeQuizLink = link => {
                        const href = normalize(link && (link.href || link.getAttribute('href') || ''));
                        return href.includes('/mod/quiz/');
                    };

                    const forbidden = text => {
                        const normalized = normalize(text);
                        return [
                            'webaula',
                            'web aula',
                            'video',
                            'material',
                            'livro',
                            'manual',
                            'lista',
                            'forum',
                            'plano de ensino'
                        ].some(term => normalized.includes(term));
                    };

                    const links = Array.from(document.querySelectorAll(
                        'a[href*="/mod/quiz/"], a[href*="mod/quiz/"], .modtype_quiz a[href]'
                    ));

                    for (const node of links) {
                        const container = node.closest('li.activity, .modtype_quiz, .activityinstance, .activity, .mod-indent-outer') || node;
                        const text = [
                            container.innerText,
                            container.textContent,
                            container.getAttribute && container.getAttribute('aria-label'),
                            container.getAttribute && container.getAttribute('title'),
                            node.innerText,
                            node.textContent,
                            node.getAttribute('aria-label'),
                            node.getAttribute('title')
                        ].filter(Boolean).join(' ');

                        if (!matches(text)) continue;
                        if (!isSafeQuizLink(node)) continue;
                        if (forbidden(text)) continue;

                        node.scrollIntoView({ block: 'center', inline: 'center' });
                        node.click();
                        return true;
                    }

                    return false;
                }""",
                {"activityKey": activity_key},
            )
        )
    except Exception:
        return False


def current_page_is_non_quiz_resource(page: Page) -> bool:
    url = normalize_search_text(page.url)
    if "/mod/quiz/" in url:
        return False
    if any(marker in url for marker in ("/mod/url/", "/mod/resource/", "/mod/page/", "/mod/book/")):
        return True
    try:
        title = normalize_search_text(page.title())
    except Exception:
        title = ""
    return is_forbidden_activity_text(title, url)


def choose_activity(page: Page, activity_choice: str) -> None:
    target_key, target_label, _ = activity_definition_for_choice(activity_choice)

    for activity_target in collect_activity_targets(page):
        if activity_target["key"] == target_key and activity_target["href"]:
            if not is_safe_activity_href(activity_target["href"]):
                continue
            page.goto(activity_target["href"], wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except PlaywrightTimeoutError:
                pass
            if current_page_is_non_quiz_resource(page):
                raise RuntimeError(
                    f"Bloqueei a abertura de um recurso que não é questionário ao tentar abrir '{target_label}'."
                )
            return

    if click_activity_by_dom_text(page, target_key):
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except PlaywrightTimeoutError:
            page.wait_for_timeout(2_000)
        if current_page_is_non_quiz_resource(page):
            raise RuntimeError(
                f"Bloqueei a abertura de um recurso que não é questionário ao tentar abrir '{target_label}'."
            )
        return

    debug_texts = "; ".join(target["text"] for target in collect_activity_targets(page)[:8])
    if debug_texts:
        raise RuntimeError(
            f"Não encontrei link seguro de questionário para '{target_label}'. Atividades detectadas: {debug_texts}"
        )
    raise RuntimeError(
        f"Não encontrei link seguro de questionário para '{target_label}'. "
        "Por segurança, não vou abrir Webaula, Material, Vídeo ou Lista."
    )

def choose_activity_with_unit_fallback(page: Page, unit_choice: str, activity_choice: str) -> None:
    last_error: Exception | None = None
    max_occurrences = count_unit_occurrences(page, unit_choice)
    if max_occurrences < 1:
        choose_unit(page, unit_choice)
        max_occurrences = 1

    for occurrence_index in range(0, max_occurrences):
        normalized_unit = normalize_unit_choice(unit_choice)
        if occurrence_index > 0:
            print(
                f"Unidade de Ensino {normalized_unit} indisponível ou incompleta. "
                f"Tentando outra ocorrência com o mesmo nome ({occurrence_index + 1}/{max_occurrences})..."
            )

        if not open_unit_occurrence(page, unit_choice, occurrence_index):
            break

        try:
            choose_activity(page, activity_choice)
            return
        except Exception as error:
            last_error = error
            try:
                if unit_is_unavailable(page):
                    remember_non_functional_unit(page)
                    continue
            except Exception:
                pass

            if occurrence_index + 1 < max_occurrences:
                continue

            raise

    if last_error:
        raise last_error

    raise RuntimeError("Não consegui abrir a atividade após testar unidades duplicadas.")


def continue_or_start_questionnaire(page: Page) -> str:
    page.wait_for_timeout(2_000)

    options = {
        "continue": re.compile(r"continuar a [uú]ltima tentativa", re.I),
        "start": re.compile(r"tentar responder o question[aá]rio agora", re.I),
        "completed": re.compile(r"fazer uma outra tentativa", re.I),
    }

    for state, option in options.items():
        locator = page.get_by_text(option)
        if locator.count():
            if state == "completed":
                return "completed"
            locator.first.click(timeout=20_000)
            return state

    raise RuntimeError(
        "Não encontrei 'CONTINUAR A ÚLTIMA TENTATIVA', "
        "'TENTAR RESPONDER O QUESTIONÁRIO AGORA' nem 'FAZER UMA OUTRA TENTATIVA' na tela."
    )


def load_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        while True:
            api_key = input("\nCole uma API key Gemini para usar o modo tutor: ").strip()
            if api_key:
                os.environ["GEMINI_API_KEY"] = api_key
                break
            print("API key obrigatória para consultar o Gemini.")

    return genai.Client(api_key=api_key)

def load_gemini_models() -> list[str]:
    configured = os.getenv(
        "GEMINI_MODELS",
        "gemini-2.5-flash-lite,gemini-2.5-flash,gemini-2.5-pro",
    )
    models = [model.strip() for model in configured.split(",") if model.strip()]
    if not models:
        raise RuntimeError("Configure ao menos um modelo em GEMINI_MODELS.")
    return models


def extract_visible_question(page: Page) -> QuizQuestion:
    page.wait_for_selector(".que, .qtext", timeout=20_000)

    question_root = page.locator(".que").first
    if not question_root.count():
        question_root = page.locator("body")

    statement_candidates = [
        question_root.locator(".qtext"),
        question_root.locator('[class*="qtext"]'),
    ]

    statement = ""
    for locator in statement_candidates:
        if locator.count():
            statement = locator.first.inner_text().strip()
            if statement:
                break

    if not statement:
        raise RuntimeError("Não consegui extrair o enunciado da questão.")

    label_candidates = [
        question_root.locator(".info .no"),
        page.get_by_text(re.compile(r"^quest[aã]o\s+\d+$", re.I)),
    ]

    label = "Questão sem número"
    for locator in label_candidates:
        if locator.count():
            candidate_text = locator.first.inner_text().strip()
            if candidate_text:
                label = candidate_text
                break

    alternative_candidates = [
        question_root.locator(".answer label"),
        question_root.locator(".answer div"),
        question_root.locator("label"),
    ]

    alternatives: list[str] = []
    for locator in alternative_candidates:
        if locator.count():
            for index in range(locator.count()):
                text = locator.nth(index).inner_text().strip()
                if text and text not in alternatives:
                    alternatives.append(text)
            if alternatives:
                break

    if not alternatives:
        raise RuntimeError("Não consegui extrair as alternativas da questão.")

    return QuizQuestion(label=label, statement=statement, alternatives=alternatives)


def capture_question_screenshot(page: Page) -> Path:
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    screenshot_path = ARTIFACTS_DIR / f"questao-{timestamp}.png"

    question_root = page.locator(".que").first
    if question_root.count():
        question_root.screenshot(path=str(screenshot_path))
    else:
        page.screenshot(path=str(screenshot_path), full_page=False)

    return screenshot_path


def build_tutor_prompt(question: QuizQuestion) -> str:
    alternatives_text = "\n".join(
        f"{index + 1}. {alternative}" for index, alternative in enumerate(question.alternatives)
    )
    return f"""
Maria está estudando esta questão e quer entender o raciocínio necessário para resolvê-la.
Leia o enunciado e as alternativas e explique passo a passo como identificar a melhor resposta,
destacando quais afirmações são verdadeiras ou falsas.
Não interaja com a página, não marque nada e não dê instruções para burlar avaliação.
Use também a imagem anexada como apoio visual, especialmente se houver fórmulas ou diagramação relevante.

Questão:
{question.statement}

Alternativas:
{alternatives_text}
""".strip()


def ask_gemini_for_explanation(client, question: QuizQuestion, screenshot_path: Path) -> str:
    prompt = build_tutor_prompt(question)
    image_bytes = screenshot_path.read_bytes()
    retry_delays = [3, 6, 12]
    models = load_gemini_models()
    last_error: Exception | None = None

    for model in models:
        print(f"Usando modelo Gemini: {model}")

        for attempt in range(len(retry_delays) + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        prompt,
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    ],
                )
                return response.text.strip()
            except genai_errors.ServerError as error:
                last_error = error
                is_unavailable = "503" in str(error) or "UNAVAILABLE" in str(error)
                is_last_attempt = attempt == len(retry_delays)

                if not is_unavailable or is_last_attempt:
                    break

                delay = retry_delays[attempt]
                print(
                    f"{model} indisponível temporariamente (tentativa {attempt + 1}). "
                    f"Vou tentar novamente em {delay} segundos..."
                )
                time.sleep(delay)
            except genai_errors.ClientError as error:
                last_error = error
                is_quota_error = "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error)
                if is_quota_error:
                    print(
                        f"{model} atingiu cota no momento. "
                        "Tentando o próximo modelo configurado..."
                    )
                    break
                raise

    if last_error:
        raise last_error

    raise RuntimeError("Falha inesperada ao consultar o Gemini.")


def show_gemini_tutor_explanation(page: Page, question: QuizQuestion | None = None) -> None:
    question = question or extract_visible_question(page)

    print(f"\n--- {question.label.upper()} CAPTURADA ---")
    print(question.statement)
    print("\n--- ALTERNATIVAS ---")
    for index, alternative in enumerate(question.alternatives, start=1):
        print(f"{index}. {alternative}")

    screenshot_path = capture_question_screenshot(page)
    print(f"\nScreenshot da questão salvo em: {screenshot_path.resolve()}")

    while True:
        client = load_gemini_client()
        print("\nConsultando o Gemini em modo tutor...")
        try:
            explanation = ask_gemini_for_explanation(client, question, screenshot_path)
            print("\n--- EXPLICAÇÃO DO GEMINI ---")
            print(explanation)
            return
        except genai_errors.ServerError as error:
            if "503" in str(error) or "UNAVAILABLE" in str(error):
                print(
                    "\nAviso: o Gemini continuou indisponível após várias tentativas. "
                    "Você pode responder manualmente e seguir o fluxo normalmente."
                )
                return
            raise
        except genai_errors.ClientError as error:
            if "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error):
                if request_new_gemini_api_key():
                    print("Nova API key recebida. Tentando novamente sem reiniciar o fluxo...")
                    continue

                print(
                    "\nSeguindo sem Gemini nesta sessão. "
                    "Você pode responder manualmente e continuar normalmente."
                )
                return
            raise


def find_next_page_button(page: Page):
    patterns = [
        re.compile(r"^pr[oó]xima p[aá]gina$", re.I),
        re.compile(r"pr[oó]xima p[aá]gina", re.I),
    ]

    for pattern in patterns:
        locator = page.get_by_text(pattern)
        if locator.count():
            for index in range(locator.count()):
                candidate = locator.nth(index)
                if candidate.is_visible():
                    return candidate
    return None


def find_button_by_text(page: Page, patterns: list[re.Pattern]):
    for pattern in patterns:
        locator = page.get_by_text(pattern)
        if locator.count():
            for index in range(locator.count()):
                candidate = locator.nth(index)
                if candidate.is_visible():
                    return candidate
    return None


def find_finish_review_href(page: Page) -> str | None:
    try:
        href = page.evaluate(
            r"""() => {
                const normalize = value => (value || '')
                    .normalize('NFD')
                    .replace(/[̀-ͯ]/g, '')
                    .replace(/\s+/g, ' ')
                    .trim()
                    .toLowerCase();

                for (const link of Array.from(document.querySelectorAll('a[href]'))) {
                    const text = normalize([
                        link.innerText,
                        link.textContent,
                        link.getAttribute('aria-label'),
                        link.getAttribute('title')
                    ].filter(Boolean).join(' '));
                    const href = link.href || link.getAttribute('href') || '';
                    if (text.includes('terminar revisao') && href) {
                        return href;
                    }
                }
                return null;
            }"""
        )
        return href or None
    except Exception:
        return None


def finish_review(page: Page) -> None:
    print("Terminando revisão...")

    # Esse botão costuma ser um <a>. Navegar direto pelo href é mais confiável
    # que clicar visualmente quando há barras fixas/scroll interferindo.
    href = find_finish_review_href(page)
    if href:
        page.goto(href, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except PlaywrightTimeoutError:
            page.wait_for_timeout(2_000)
        return

    finish_review_button = find_button_by_text(
        page,
        [
            re.compile(r"^terminar revis[aã]o$", re.I),
            re.compile(r"terminar revis[aã]o", re.I),
        ],
    )
    if finish_review_button is None:
        raise RuntimeError("Não encontrei o botão 'TERMINAR REVISÃO'.")

    try:
        finish_review_button.scroll_into_view_if_needed(timeout=5_000)
    except Exception:
        pass

    try:
        finish_review_button.click(timeout=20_000, force=True)
    except Exception:
        clicked = page.evaluate(
            r"""() => {
                const normalize = value => (value || '')
                    .normalize('NFD')
                    .replace(/[̀-ͯ]/g, '')
                    .replace(/\s+/g, ' ')
                    .trim()
                    .toLowerCase();
                for (const link of Array.from(document.querySelectorAll('a[href], button, [role="button"]'))) {
                    const text = normalize([link.innerText, link.textContent, link.getAttribute('aria-label'), link.getAttribute('title')].filter(Boolean).join(' '));
                    if (text.includes('terminar revisao')) {
                        link.click();
                        return true;
                    }
                }
                return false;
            }"""
        )
        if not clicked:
            raise

    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PlaywrightTimeoutError:
        page.wait_for_timeout(2_000)


def finalize_attempt_flow(page: Page) -> None:
    finalize_button = find_button_by_text(
        page,
        [
            re.compile(r"^finalizar tentativa\.{0,3}$", re.I),
            re.compile(r"finalizar tentativa", re.I),
        ],
    )
    if finalize_button is None:
        raise RuntimeError(
            "Não encontrei nem 'Próxima Página' nem 'Finalizar Tentativa' ao fim do questionário."
        )

    print("\nFinalizando tentativa...")
    finalize_button.click(timeout=20_000)
    page.wait_for_timeout(2_000)

    send_all_button = find_button_by_text(
        page,
        [
            re.compile(r"^enviar tudo e terminar$", re.I),
            re.compile(r"enviar tudo e terminar", re.I),
        ],
    )
    if send_all_button is None:
        raise RuntimeError("Não encontrei o botão 'ENVIAR TUDO E TERMINAR'.")

    print("Enviando tudo e terminando...")
    send_all_button.click(timeout=20_000)
    page.wait_for_timeout(1_500)

    confirmation_dialog = page.locator(
        ".moodle-dialogue-confirm[aria-hidden='false'], "
        ".moodle-dialogue-base.moodle-dialogue-confirm[aria-hidden='false']"
    )

    confirm_button = None
    if confirmation_dialog.count():
        modal_candidates = confirmation_dialog.last.get_by_text(
            re.compile(r"^enviar tudo e (terminar|confirmar)$", re.I)
        )
        if modal_candidates.count():
            confirm_button = modal_candidates.first

    if confirm_button is None:
        confirm_button = find_button_by_text(
            page,
            [
                re.compile(r"^enviar tudo e terminar$", re.I),
                re.compile(r"^enviar tudo e confirmar$", re.I),
                re.compile(r"enviar tudo e (terminar|confirmar)", re.I),
            ],
        )

    if confirm_button is None:
        raise RuntimeError(
            "Não encontrei o botão de confirmação final 'ENVIAR TUDO E TERMINAR' ou 'ENVIAR TUDO E CONFIRMAR'."
        )

    print("Confirmando envio final...")
    confirm_button.click(timeout=20_000, force=True)
    page.wait_for_timeout(2_500)

    finish_review(page)


def process_quiz_pages(page: Page) -> None:
    page_number = 1

    while True:
        current_question = extract_visible_question(page)
        print(
            f"\n================ PÁGINA {page_number} | {current_question.label.upper()} ================"
        )
        show_gemini_tutor_explanation(page, current_question)

        input(
            "\nSelecione sua resposta manualmente no navegador e pressione Enter aqui "
            "para avançar..."
        )

        next_button = find_next_page_button(page)
        if next_button is None:
            print("\nNão há mais botão 'Próxima Página'.")
            finalize_attempt_flow(page)
            return

        previous_question_text = page.locator(".qtext").first.inner_text().strip()
        next_button.click(timeout=20_000)
        page.wait_for_timeout(2_000)

        try:
            page.wait_for_function(
                """previousText => {
                    const current = document.querySelector('.qtext');
                    return current && current.innerText.trim() !== previousText;
                }""",
                arg=previous_question_text,
                timeout=20_000,
            )
        except PlaywrightTimeoutError:
            page.wait_for_load_state("networkidle")

        page_number += 1


def ask_post_review_action(
    include_same_section: bool = False,
    same_level_label: str = "Escolher outra unidade",
) -> str:
    section_context = "seção" in normalize_search_text(same_level_label)

    while True:
        print("\nO que deseja fazer agora?")
        if include_same_section:
            print("1 - Manter na mesma seção")
            print(f"2 - {same_level_label}")
            print("3 - Escolher outra unidade")
            print("4 - Escolher outra matéria")
            print("5 - Sair")
            valid = {"1", "2", "3", "4", "5"}
        elif section_context:
            print(f"1 - {same_level_label}")
            print("2 - Escolher outra unidade")
            print("3 - Escolher outra matéria")
            print("4 - Sair")
            valid = {"1", "2", "3", "4"}
        else:
            print(f"1 - {same_level_label}")
            print("2 - Escolher outra matéria")
            print("3 - Sair")
            valid = {"1", "2", "3"}

        choice = input("Digite o número da opção: ").strip()
        if choice not in valid:
            print("Opção inválida. Escolha um número da lista.")
            continue

        if include_same_section:
            if choice == "1":
                return "same_section"
            if choice == "2":
                return "other_section"
            if choice == "3":
                return "same_discipline"
            if choice == "4":
                return "other_discipline"
            return "exit"

        if section_context:
            if choice == "1":
                return "other_section"
            if choice == "2":
                return "same_discipline"
            if choice == "3":
                return "other_discipline"
            return "exit"

        if choice == "1":
            return "same_discipline"
        if choice == "2":
            return "other_discipline"
        return "exit"


def return_to_disciplines(page: Page) -> None:
    page.goto("https://www.avaeduc.com.br/", wait_until="networkidle")
    accept_cookies_if_present(page)


def handle_questionnaire_flow(
    page: Page,
    include_same_section: bool = False,
    same_level_label: str = "Escolher outra unidade",
) -> str:
    print("Procurando a ação disponível do questionário...")
    questionnaire_state = continue_or_start_questionnaire(page)

    if questionnaire_state == "completed":
        print("\nATIVIDADE FEITA.")
        return ask_post_review_action(
            include_same_section=include_same_section,
            same_level_label=same_level_label,
        )

    print("Iniciando fluxo assistido das páginas do questionário...")
    process_quiz_pages(page)

    return ask_post_review_action(
        include_same_section=include_same_section,
        same_level_label=same_level_label,
    )


def ask_after_empty_section() -> str:
    print("\nSEÇÃO SEM ATIVIDADES.")
    return ask_post_review_action(
        include_same_section=False,
        same_level_label="Escolher outra seção",
    )


def run_activity_cycle(page: Page) -> str:
    unit_choice = ask_unit_choice(page)
    if unit_choice == "sair":
        return "exit"

    normalized_unit = normalize_unit_choice(unit_choice)
    print(f"Acessando unidade: Unidade de Ensino {normalized_unit}")

    section_links = get_expandable_section_links(page, unit_choice)
    if section_links:
        selected_section: UnitLink | None = None

        while True:
            if selected_section is None:
                selected_section = ask_section_choice(section_links)

            section_number = extract_section_number(selected_section.text)
            print(f"Acessando Seção {section_number} da Unidade de Ensino {normalized_unit}")
            page.goto(selected_section.href, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1_500)

            activity_options = visible_activity_options(page)
            if not activity_options:
                if unit_is_unavailable(page):
                    print("Aviso: encontrei aviso de disponibilidade futura e nenhuma atividade reconhecida.")
                else:
                    print("Aviso: nenhuma atividade reconhecida no texto/HTML da seção.")

                action = ask_after_empty_section()
                if action == "other_section":
                    selected_section = None
                    continue
                return action

            activity_choice = ask_activity_choice(activity_options)
            print("Abrindo opção escolhida...")
            try:
                choose_activity(page, activity_choice)
            except RuntimeError as error:
                message = str(error)
                if "link seguro" in message or "Bloqueei" in message:
                    print(f"\n{message}")
                    action = ask_after_empty_section()
                    if action == "other_section":
                        selected_section = None
                        continue
                    return action
                raise

            action = handle_questionnaire_flow(
                page,
                include_same_section=True,
                same_level_label="Escolher outra seção",
            )
            if action == "same_section":
                continue
            if action == "other_section":
                selected_section = None
                continue
            return action

    choose_unit(page, unit_choice)
    page.wait_for_load_state("networkidle")

    if unit_is_unavailable(page):
        print("\nUNIDADE SEM ATIVIDADES.")
        return ask_post_review_action()

    activity_options = classic_activity_options(page)
    activity_choice = ask_activity_choice(activity_options)
    print("Abrindo opção escolhida...")
    choose_activity_with_unit_fallback(page, unit_choice, activity_choice)

    return handle_questionnaire_flow(page)

def main() -> None:
    credentials = load_credentials()
    configure_session_gemini_api_key()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=env_flag("HEADLESS", default=False))
        context = browser.new_context()
        page = context.new_page()

        try:
            while True:
                if perform_login(page, credentials):
                    break

                print("\nUsuário ou Senha inválidos, tente novamente.\n")
                credentials = load_credentials()

            print("Tratando comunicado inicial...")
            dismiss_initial_announcement(page)

            print("Abrindo área Estudar...")
            ava_page = go_to_study_area(page)
            ava_page.wait_for_url(re.compile(AVA_URL_FRAGMENT), timeout=30_000)
            ava_page.wait_for_load_state("networkidle")
            accept_cookies_if_present(ava_page)

            while True:
                discipline_name = ask_user_to_choose_discipline(ava_page)
                print(f"Acessando disciplina: {discipline_name}")
                choose_discipline(ava_page, discipline_name)
                ava_page.wait_for_load_state("networkidle")

                while True:
                    cycle_result = run_activity_cycle(ava_page)

                    if cycle_result == "same_discipline":
                        print(
                            "\nAtividade concluída. Você pode escolher outra unidade na mesma matéria."
                        )
                        continue

                    if cycle_result == "other_discipline":
                        print("\nVoltando para a lista de matérias...")
                        return_to_disciplines(ava_page)
                        break

                    if cycle_result == "exit":
                        print("\nEncerrando o ciclo de atividades.")
                        break

                if cycle_result == "exit":
                    break

            print("Fluxo concluído. O navegador continuará aberto para conferência.")
            input("Pressione Enter para fechar o navegador...")
        except Exception as error:
            ARTIFACTS_DIR.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            screenshot_path = ARTIFACTS_DIR / f"erro-{timestamp}.png"
            html_path = ARTIFACTS_DIR / f"erro-{timestamp}.html"

            try:
                current_page = context.pages[-1]
                current_page.screenshot(path=str(screenshot_path), full_page=True)
                html_path.write_text(current_page.content(), encoding="utf-8")
            except Exception:
                pass

            print("\nO fluxo parou antes do fim.")
            print(f"Erro: {error}")
            print("\nDetalhes técnicos:")
            traceback.print_exc()
            print(f"\nScreenshot salvo em: {screenshot_path.resolve()}")
            print(f"HTML salvo em: {html_path.resolve()}")
            input("\nPressione Enter para fechar o navegador...")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
