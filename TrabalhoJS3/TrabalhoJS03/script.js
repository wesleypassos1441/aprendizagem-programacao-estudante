// Array inicial com dados aleatórios de candidatos
let candidatos = [
    { nome: "Ana Silva", idade: 32, horasVoo: 1500, notaPsico: 8.5 },
    { nome: "Bruno Costa", idade: 28, horasVoo: 800, notaPsico: 9.0 },
    { nome: "Carlos Souza", idade: 35, horasVoo: 2000, notaPsico: 7.5 },
    { nome: "Diana Santos", idade: 29, horasVoo: 1200, notaPsico: 8.2 },
    { nome: "Eduardo Oliveira", idade: 41, horasVoo: 2500, notaPsico: 8.8 },
    { nome: "Fernanda Lima", idade: 26, horasVoo: 950, notaPsico: 7.8 },
    { nome: "Gabriel Martins", idade: 38, horasVoo: 1800, notaPsico: 8.6 },
    { nome: "Helena Rocha", idade: 31, horasVoo: 1400, notaPsico: 9.1 },
    { nome: "Igor Ferreira", idade: 27, horasVoo: 1100, notaPsico: 8.3 },
    { nome: "Julia Alves", idade: 34, horasVoo: 2200, notaPsico: 8.9 },
    { nome: "Kevin Gomes", idade: 25, horasVoo: 700, notaPsico: 7.9 },
    { nome: "Larissa Pereira", idade: 33, horasVoo: 1600, notaPsico: 8.4 },
    { nome: "Marcelo Ribeiro", idade: 42, horasVoo: 2800, notaPsico: 8.7 },
    { nome: "Natalia Cardoso", idade: 30, horasVoo: 1350, notaPsico: 8.1 },
    { nome: "Otavio Mendes", idade: 36, horasVoo: 1950, notaPsico: 8.5 }
];

// Critérios da Missão Marte 2030
const CRITERIOS = {
    idadeMinima: 25,
    idadeMaxima: 45,
    horasVooMinima: 1000,
    notaPsicoMinima: 8
};

// Função para avaliar um candidato
function avaliarCandidato(candidato) {
    return candidato.idade >= CRITERIOS.idadeMinima &&
           candidato.idade <= CRITERIOS.idadeMaxima &&
           candidato.horasVoo >= CRITERIOS.horasVooMinima &&
           candidato.notaPsico >= CRITERIOS.notaPsicoMinima;
}

// Função para adicionar um novo candidato
function adicionarCandidato() {
    // Obter valores dos inputs
    const nome = document.getElementById("nome").value.trim();
    const idade = Number(document.getElementById("idade").value);
    const horasVoo = Number(document.getElementById("horasVoo").value);
    const notaPsico = Number(document.getElementById("notaPsico").value);

    // Validar se todos os campos foram preenchidos
    if (!nome || !idade || !horasVoo || !notaPsico) {
        alert("Por favor, preencha todos os campos!");
        return;
    }

    // Validar valores
    if (idade < 18 || idade > 65) {
        alert("Idade deve estar entre 18 e 65 anos!");
        return;
    }

    if (horasVoo < 0) {
        alert("Horas de voo não pode ser negativa!");
        return;
    }

    if (notaPsico < 0 || notaPsico > 10) {
        alert("Nota psicológica deve estar entre 0 e 10!");
        return;
    }

    // Criar novo objeto candidato
    const novoCandidato = {
        nome: nome,
        idade: idade,
        horasVoo: horasVoo,
        notaPsico: notaPsico
    };

    // Adicionar ao array candidatos
    candidatos.push(novoCandidato);

    // Avaliar o candidato
    const isApto = avaliarCandidato(novoCandidato);
    const resultado = document.getElementById("resultado");
    
    if (isApto) {
        resultado.innerHTML = `${nome} foi <strong>APROVADO</strong> para a Missão Marte 2030!`;
        resultado.className = "apto";
    } else {
        resultado.innerHTML = `${nome} foi <strong>REPROVADO</strong>. Não atende aos critérios da missão.`;
        resultado.className = "inapto";
    }
    resultado.style.display = "block";

    // Limpar formulário
    document.getElementById("nome").value = "";
    document.getElementById("idade").value = "";
    document.getElementById("horasVoo").value = "";
    document.getElementById("notaPsico").value = "";

    console.log(`Candidato adicionado: ${nome}. Total de candidatos: ${candidatos.length}`);
}

// Função para exibir os resultados
function exibirResultados() {
    const resultsContainer = document.getElementById("resultsContainer");
    resultsContainer.style.display = "block";

    // Separar candidatos em aptos e inaptos
    const aptos = candidatos.filter(c => avaliarCandidato(c));
    const inaptos = candidatos.filter(c => !avaliarCandidato(c));

    // Filtros especiais usando o método filter()
    const maiorIdade = candidatos.filter(c => c.idade > 30);
    const maiorVoo = candidatos.filter(c => c.horasVoo > 2000);
    const maiorPsico = candidatos.filter(c => c.notaPsico > 8.0);

    // Preencher coluna de Aptos
    const aptosColumn = document.getElementById("aptosColumn");
    if (aptos.length > 0) {
        aptosColumn.innerHTML = aptos.map(c => 
            `<div class="candidate-item">
                <strong>${c.nome}</strong>
                <small>Idade: ${c.idade} | Voo: ${c.horasVoo}h | Psico: ${c.notaPsico}</small>
            </div>`
        ).join("");
    } else {
        aptosColumn.innerHTML = '<div class="empty-message">Nenhum candidato apto</div>';
    }

    // Preencher coluna de Inaptos
    const inaptosColumn = document.getElementById("inaptosColumn");
    if (inaptos.length > 0) {
        let html = "";
        for (let i = 0; i < inaptos.length; i++) {
            const c = inaptos[i];
            html += `<div class="candidate-item">
                        <strong>${c.nome}</strong>
                        <small>Idade: ${c.idade} | Voo: ${c.horasVoo}h | Psico: ${c.notaPsico}</small>
                     </div>`;
        }
        inaptosColumn.innerHTML = html;
    } else {
        inaptosColumn.innerHTML = '<div class="empty-message">Nenhum candidato inapto</div>';
    }

    // Preencher coluna de idade maior que 30
    const maiorIdadeColumn = document.getElementById("maiorIdadeColumn");
    if (maiorIdade.length > 0) {
        maiorIdadeColumn.innerHTML = maiorIdade.map(c => 
            `<div class="candidate-item">
                <strong>${c.nome}</strong>
                <small>Idade: ${c.idade} anos</small>
            </div>`
        ).join("");
    } else {
        maiorIdadeColumn.innerHTML = '<div class="empty-message">Nenhum candidato</div>';
    }

    // Preencher coluna de horas de voo mais de 2000
    const maiorVooColumn = document.getElementById("maiorVooColumn");
    if (maiorVoo.length > 0) {
        maiorVooColumn.innerHTML = maiorVoo.map(c => 
            `<div class="candidate-item">
                <strong>${c.nome}</strong>
                <small>Voo: ${c.horasVoo}h</small>
            </div>`
        ).join("");
    } else {
        maiorVooColumn.innerHTML = '<div class="empty-message">Nenhum candidato</div>';
    }
    
    // Preencher coluna de psico mais de 8
    const maiorPsicoColumn = document.getElementById("maiorPsicoColumn");
    if (maiorPsico.length > 0) {
        maiorPsicoColumn.innerHTML = maiorPsico.map(c => 
            `<div class="candidate-item">
                <strong>${c.nome}</strong>
                <small>Psico: ${c.notaPsico}</small>
            </div>`
        ).join("");
    } else {
        maiorPsicoColumn.innerHTML = '<div class="empty-message">Nenhum candidato</div>';
    }

    // Calcular estatísticas com contagem e reduce()
    const total = candidatos.length;
    
    // Calcular taxa de aprovação
    const taxaAprovacao = total > 0 ? ((aptos.length / total) * 100).toFixed(1) : 0;
    
    // Calcular soma das idades usando reduce e depois a média
    const somaIdades = candidatos.reduce((acumulador, c) => acumulador + c.idade, 0);
    const mediaIdade = total > 0 ? (somaIdades / total).toFixed(1) : 0;
    
    // Calcular soma das horas de voo usando reduce e depois a média
    const somaVoos = candidatos.reduce((acumulador, c) => acumulador + c.horasVoo, 0);
    const mediaVoo = total > 0 ? (somaVoos / total).toFixed(1) : 0;

    // Atualizar estatísticas no HTML
    document.getElementById("totalCandidatos").innerHTML = total;
    document.getElementById("taxaAprovacao").innerHTML = `${taxaAprovacao}%`;
    document.getElementById("idadeMedia").innerHTML = mediaIdade;
    document.getElementById("vooMedia").innerHTML = mediaVoo;

    console.log(`Resultados exibidos: ${aptos.length} aptos, ${inaptos.length} inaptos`);
}