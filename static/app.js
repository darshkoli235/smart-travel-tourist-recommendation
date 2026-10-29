// Keep the trip-budget value visible while the user moves the slider.
const budgetSlider = document.querySelector("#budget");
const budgetValue = document.querySelector("#budget-value");

if (budgetSlider && budgetValue) {
  const showBudget = () => {
    const value = Number(budgetSlider.value).toLocaleString("en-IN");
    budgetValue.textContent = `₹${value}`;
  };

  budgetSlider.addEventListener("input", showBudget);
  showBudget();
}

// Open the compact navigation on small screens.
const menuButton = document.querySelector(".menu-toggle");
const siteNavigation = document.querySelector("#site-nav");

if (menuButton && siteNavigation) {
  menuButton.addEventListener("click", () => {
    const isOpen = menuButton.getAttribute("aria-expanded") === "true";
    menuButton.setAttribute("aria-expanded", String(!isOpen));
    siteNavigation.classList.toggle("nav-open", !isOpen);
  });
}
