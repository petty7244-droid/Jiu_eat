document.addEventListener("DOMContentLoaded", () => {

    function loadHeader(html) {
        document.body.insertAdjacentHTML("afterbegin", html);
        const hamburger = document.getElementById("hamburger-btn");
        const navLinks = document.getElementById("nav-links");
        if (hamburger && navLinks) {
            hamburger.addEventListener("click", () => {
                navLinks.classList.toggle("open");
            });
        }
    }

    function loadFooter(html) {
        document.body.insertAdjacentHTML("beforeend", html);
    }

    fetch("header.html")
        .then(r => r.text())
        .then(loadHeader)
        .catch(() => {
            loadHeader(`
<header>
    <a href="index.html" class="logo">
        <span>Jiu-eat</span>
    </a>
    <button class="hamburger" id="hamburger-btn" aria-label="選單">&#9776;</button>
    <ul class="nav-links" id="nav-links">
        <li><a href="index.html">探索聚會</a></li>
        <li><a href="#">主題動態</a></li>
        <li><a href="#">開團教學</a></li>
        <li><a href="register.html" class="btn-primary">會員登入</a></li>
        <li><a href="#" class="btn-primary">發起聚會</a></li>
    </ul>
</header>
`);
        });

    fetch("footer.html")
        .then(r => r.text())
        .then(loadFooter)
        .catch(() => {
            loadFooter(`
<footer>
    <p>&copy; Jiu-eat - 揪食聚會活動平台</p>
</footer>
`);
        });
});
