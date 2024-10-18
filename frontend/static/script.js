$(document).ready(function() {
    // Add a random delay to each product card animation for a staggered effect
    $('.product-card').each(function() {
        let delay = Math.floor(Math.random() * 500);
        $(this).css('animation-delay', delay + 'ms');
    });
});
