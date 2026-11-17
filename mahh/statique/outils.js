// Bouton « Utiliser ma position » à côté de chaque champ Latitude.
// Le téléphone de l’agent ou de l’abonné remplit latitude et longitude.
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-regenerer]").forEach(function (bouton) {
    bouton.addEventListener("click", function () {
      var cible = document.getElementById(bouton.getAttribute("data-regenerer"));
      if (!cible) return;
      var alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
      var mot = "";
      var tirage = new Uint32Array(12);
      crypto.getRandomValues(tirage);
      for (var i = 0; i < tirage.length; i++) mot += alphabet[tirage[i] % alphabet.length];
      cible.value = mot;
    });
  });
  if (!("geolocation" in navigator)) return;
  document.querySelectorAll('input[name="latitude"]').forEach(function (lat) {
    var form = lat.form;
    if (!form) return;
    var lon = form.querySelector('input[name="longitude"]');
    if (!lon) return;
    var bouton = document.createElement("button");
    bouton.type = "button";
    bouton.className = "secondaire gps";
    bouton.textContent = "Utiliser ma position";
    bouton.addEventListener("click", function () {
      bouton.disabled = true;
      bouton.textContent = "Recherche de la position…";
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          lat.value = pos.coords.latitude.toFixed(6);
          lon.value = pos.coords.longitude.toFixed(6);
          bouton.disabled = false;
          bouton.textContent = "Position relevée (±" + Math.round(pos.coords.accuracy) + " m)";
        },
        function () {
          bouton.disabled = false;
          bouton.textContent = "Position refusée — saisissez-la à la main";
        },
        { enableHighAccuracy: true, timeout: 15000 }
      );
    });
    lat.parentNode.insertBefore(bouton, lat);
  });
});
