// Hierarquia de escolaridade (quanto maior o número, maior o grau)
const PESO_ESCOLARIDADE = {
    "Ensino Fundamental Incompleto": 1,
    "Ensino Fundamental Completo": 2,
    "Ensino Médio Incompleto": 3,
    "Ensino Médio Completo": 4,
    "Ensino Superior Incompleto": 5,
    "Ensino Superior em Andamento": 6,
    "Ensino Superior Completo": 7
};

// Lógica de Triagem por Vaga
const REGRAS_VAGAS = {
    "Jovem Aprendiz": (idade, pesoEscolaridade) => {
        // Idade entre 14 e 24 anos. Escolaridade entre Fundamental Incompleto e Médio Completo
        return idade >= 14 && idade <= 24 && pesoEscolaridade >= 1 && pesoEscolaridade <= 4;
    },
    "Estágio Superior": (idade, pesoEscolaridade) => {
        // Idade mínima 16 anos. Deve estar com o Ensino Superior em Andamento (Peso 6)
        return idade >= 16 && pesoEscolaridade === 6;
    },
    "Serviços Gerais": (idade, pesoEscolaridade) => {
        // Idade mínima 18 anos. Mínimo: Fundamental Completo (Peso 2+)
        return idade >= 18 && pesoEscolaridade >= 2;
    },
    "Analista Sênior": (idade, pesoEscolaridade) => {
        // Idade mínima 18 anos. Mínimo: Superior Completo (Peso 7)
        return idade >= 18 && pesoEscolaridade === 7;
    }
};

// Array inicial com dados fictícios
let candidatos = [];

// Máscara de CPF
function aplicarMascaraCPF(input) {
    let value = input.value.replace(/\D/g, "");
    if (value.length > 11) value = value.slice(0, 11);
    value = value.replace(/(\d{3})(\d)/, "$1.$2");
    value = value.replace(/(\d{3})(\d)/, "$1.$2");
    value = value.replace(/(\d{3})(\d{1,2})$/, "$1-$2");
    input.value = value;
}

// Calcular idade
function calcularIdade(dataNascimento) {
    const hoje = new Date();
    const nascimento = new Date(dataNascimento);
    let idade = hoje.getFullYear() - nascimento.getFullYear();
    const mes = hoje.getMonth() - nascimento.getMonth();
    if (mes < 0 || (mes === 0 && hoje.getDate() < nascimento.getDate())) {
        idade--;
    }
    return idade;
}

// Função de avaliação baseada na vaga escolhida
function avaliarCandidato(candidato) {
    const pesoEscolaridade = PESO_ESCOLARIDADE[candidato.escolaridade];
    const avaliador = REGRAS_VAGAS[candidato.vaga];
    
    // Retorna se o candidato passou na regra da vaga
    return avaliador ? avaliador(candidato.idade, pesoEscolaridade) : false;
}

// Adicionar Candidato
function adicionarCandidato() {
    const nome = document.getElementById("nome").value.trim();
    const cpf = document.getElementById("cpf").value.trim();
    const dataNascimento = document.getElementById("dataNascimento").value;
    const escolaridade = document.getElementById("escolaridade").value;
    const vaga = document.getElementById("vaga").value;

    if (!nome || !cpf || !dataNascimento || !escolaridade || !vaga) {
        alert("Por favor, preencha todos os campos!");
        return;
    }

    if (cpf.length !== 14) {
        alert("Por favor, digite um CPF válido com 11 dígitos!");
        return;
    }

    const idade = calcularIdade(dataNascimento);
    const novoCandidato = { nome, cpf, dataNascimento, idade, escolaridade, vaga };
    
    candidatos.push(novoCandidato);

    const isApto = avaliarCandidato(novoCandidato);
    const resultado = document.getElementById("resultado");
    
    if (isApto) {
        resultado.innerHTML = `${nome} foi <strong>APROVADO(A)</strong> na triagem para a vaga de <strong>${vaga}</strong>!`;
        resultado.className = "apto";
    } else {
        resultado.innerHTML = `${nome} <strong>NÃO ATENDE</strong> aos requisitos da vaga de <strong>${vaga}</strong>.`;
        resultado.className = "inapto";
    }
    resultado.style.display = "block";

    // Limpar formulário
    document.getElementById("nome").value = "";
    document.getElementById("cpf").value = "";
    document.getElementById("dataNascimento").value = "";
    document.getElementById("escolaridade").selectedIndex = 0;
    document.getElementById("vaga").selectedIndex = 0;
}

// Exibir Resultados
function exibirResultados() {
    document.getElementById("resultsContainer").style.display = "block";

    const aptos = candidatos.filter(c => avaliarCandidato(c));
    const inaptos = candidatos.filter(c => !avaliarCandidato(c));

    const iniciantes = candidatos.filter(c => c.vaga === "Jovem Aprendiz" || c.vaga === "Estágio Superior");
    const operacionais = candidatos.filter(c => c.vaga === "Serviços Gerais");
    const especialistas = candidatos.filter(c => c.vaga === "Analista Sênior");

    // Helper para gerar o HTML do card do candidato
    const gerarCard = (c) => `
        <div class="candidate-item">
            <strong>${c.nome}</strong>
            <small>Idade: ${c.idade} | CPF: ${c.cpf}</small>
            <small>🎓 ${c.escolaridade}</small>
            <small style="color: #2b5876; font-weight: bold; margin-top: 5px;">📌 Vaga: ${c.vaga}</small>
        </div>`;

    document.getElementById("aptosColumn").innerHTML = aptos.length > 0 ? aptos.map(gerarCard).join("") : '<div class="empty-message">Nenhum aprovado</div>';
    document.getElementById("inaptosColumn").innerHTML = inaptos.length > 0 ? inaptos.map(gerarCard).join("") : '<div class="empty-message">Nenhum reprovado</div>';
    
    document.getElementById("iniciantesColumn").innerHTML = iniciantes.length > 0 ? iniciantes.map(gerarCard).join("") : '<div class="empty-message">Vazio</div>';
    document.getElementById("operacionalColumn").innerHTML = operacionais.length > 0 ? operacionais.map(gerarCard).join("") : '<div class="empty-message">Vazio</div>';
    document.getElementById("especialistasColumn").innerHTML = especialistas.length > 0 ? especialistas.map(gerarCard).join("") : '<div class="empty-message">Vazio</div>';

    const total = candidatos.length;
    const taxaAprovacao = total > 0 ? ((aptos.length / total) * 100).toFixed(1) : 0;

    document.getElementById("totalCandidatos").innerHTML = total;
    document.getElementById("taxaAprovacao").innerHTML = `${taxaAprovacao}%`;
}