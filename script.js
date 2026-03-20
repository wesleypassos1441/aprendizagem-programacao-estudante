// TODO: Implemente a função avaliarCandidato() aqui
// Dicas:
// 1. Pegue os valores dos inputs usando getElementById() e .value
// 2. Converta os valores para número usando Number()
// 3. Declare variáveis para armazenar os valores
// 4. Use if/else para verificar os critérios
// 5. Atualize o parágrafo com id="resultado" usando innerHTML
// 6. Adicione a classe apropriada (.apto ou .inapto) usando classList.add()

function avaliarCandidato() {
     // Seu código aqui...
    let idade = Number(document.getElementById('idade').value);
    let horasVoo = Number(document.getElementById('voo').value);
    let notaPsi = Number(document.getElementById('psi').value);
    let resultado = document.getElementById('resultado');

    resultado.className = ''; 
    resultado.style.display = 'block';

    if (idade < 25 || idade > 45) {
        resultado.innerHTML = "Inapto: Idade inadequada. O candidato deve ter entre 25 e 45 anos.";
        resultado.classList.add('inapto');
        
    } else if (horasVoo < 1000) {
        resultado.innerHTML = "Inapto: Horas de voo insuficientes. Requisito mínimo de 1.000 horas.";
        resultado.classList.add('inapto');
        
    } else if (notaPsi < 8) {
        resultado.innerHTML = "Inapto: Nota psicológica abaixo do exigido. Requisito mínimo é 8.";
        resultado.classList.add('inapto');
        
    } else {
        resultado.innerHTML = "Apto! O candidato atende a todos os requisitos da Missão Marte 2030.";
        resultado.classList.add('apto');
    }
}