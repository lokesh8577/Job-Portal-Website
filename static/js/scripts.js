function Toggle_show() {
    const dropdown = document.getElementById('avatar-dropdown');
    dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
  }
  
  // Close dropdown when clicking outside
  document.addEventListener('click', function(event) {
    const avatarBtn = document.getElementById('avatar-btn');
    const dropdown = document.getElementById('avatar-dropdown');
    
    if (!avatarBtn.contains(event.target) && !dropdown.contains(event.target)) {
      dropdown.style.display = 'none';
    }
  });