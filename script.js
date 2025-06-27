// Simple script to show a message on form submission
const form = document.querySelector('form');
form.addEventListener('submit', function (e) {
  e.preventDefault();
  alert('Gracias por contactar con Ergo. Te responderemos pronto.');
  form.reset();
});
