// Переменные для хранения реальных данных видео из GCS
let videoData = [];

// Функция для создания карточки видео
function createVideoCard(videoData, delay = 0) {
    const card = document.createElement('div');
    card.className = 'video-card';
    card.style.animationDelay = `${delay}ms`;
    
    // Добавляем обработчик клика, который перенаправляет на страницу видео
    card.onclick = function() {
        // Используем video_id из GCS
        window.location.href = `/video/${videoData.video_id}/`;
    };

    // Определяем путь к превью, с запасным вариантом
    const previewPath = videoData.thumbnail_url ? 
        videoData.thumbnail_url : 
        `/static/placeholder.jpg`;

    card.innerHTML = `
        <div class="thumbnail">
            <img src="${previewPath}" onerror="this.src='/static/placeholder.jpg'" alt="${videoData.title}">
            <div class="duration">${videoData.duration || "00:00"}</div>
        </div>
        <div class="video-info">
            <div class="video-title">${videoData.title}</div>
            <div class="channel-name">${videoData.user_id || ""}</div>
            <div class="video-stats">
                <span>${videoData.views || "0"} просмотров</span>
                <span>• ${videoData.upload_date ? videoData.upload_date.slice(0, 10) : "Недавно"}</span>
            </div>
        </div>
    `;

    return card;
}

// Переменные для управления загрузкой
let currentIndex = 0;
const videosPerPage = 15;
let loadingSpinner, videosContainer;
let isLoading = false;

// Загрузка видео из GCS
function loadVideosFromGCS() {
    // Получаем API URL для списка видео
    fetch('/api/list-videos/')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.videos) {
                // Сохраняем полученные видео
                videoData = data.videos;
                
                // Добавляем видео в контейнер
                if (videosContainer) {
                    // Очищаем существующие видео (если есть)
                    videosContainer.innerHTML = '';
                    
                    // Добавляем новые видео
                    for (let i = 0; i < Math.min(videosPerPage, videoData.length); i++) {
                        const card = createVideoCard(videoData[i], i * 100);
                        videosContainer.appendChild(card);
                        currentIndex++;
                    }
                    
                    // Если нет видео, показываем сообщение
                    if (videoData.length === 0) {
                        const emptyState = document.createElement('div');
                        emptyState.className = 'empty-state';
                        emptyState.innerHTML = `
                            <div style="text-align: center; padding: 40px 20px;">
                                <div style="font-size: 48px; margin-bottom: 20px;">🐰</div>
                                <h3>Пока нет видео</h3>
                                <p>Видео появятся здесь, когда авторы начнут их загружать</p>
                            </div>
                        `;
                        videosContainer.appendChild(emptyState);
                    }
                }
            }
        })
        .catch(error => {
            console.error('Ошибка при получении видео из GCS:', error);
        });
}

// Загрузка дополнительных видео
function loadMoreVideos() {
    if (isLoading || currentIndex >= videoData.length) return;
    
    loadingSpinner = document.getElementById('loading-spinner');
    isLoading = true;
    if (loadingSpinner) loadingSpinner.style.display = 'flex';
    
    // Имитация загрузки для плавности
    setTimeout(() => {
        const limit = Math.min(currentIndex + videosPerPage, videoData.length);
        
        for (let i = currentIndex; i < limit; i++) {
            const card = createVideoCard(videoData[i], (i - currentIndex) * 100);
            videosContainer.appendChild(card);
        }
        
        currentIndex = limit;
        isLoading = false;
        if (loadingSpinner) loadingSpinner.style.display = 'none';
    }, 500);
}

// Обработчик прокрутки для бесконечной загрузки
function handleScroll() {
    if (!videosContainer) return;
    
    // Проверяем, достиг ли пользователь конца текущих видео
    const lastVideoCard = videosContainer.querySelector('.video-card:last-child');
    
    if (lastVideoCard) {
        const lastVideoRect = lastVideoCard.getBoundingClientRect();
        // Загружаем новые видео только когда последняя карточка видео видна в области просмотра
        if (lastVideoRect.bottom <= window.innerHeight && !isLoading) {
            loadMoreVideos();
        }
    }
}

// Функция для поиска видео
function searchVideos(query) {
    if (!query.trim() || !videoData.length) return [];
    
    query = query.toLowerCase();
    return videoData.filter(video => 
        (video.title && video.title.toLowerCase().includes(query)) || 
        (video.user_id && video.user_id.toLowerCase().includes(query))
    );
}

// Функция для отображения результатов поиска в выпадающем списке
function showSearchResults(results, searchDropdown) {
    if (!searchDropdown) return;
    
    searchDropdown.innerHTML = '';
    
    if (results.length === 0) {
        searchDropdown.classList.remove('show');
        return;
    }
    
    // Ограничиваем количество результатов для выпадающего списка
    const displayResults = results.slice(0, 5);
    
    displayResults.forEach(video => {
        // Определяем путь к превью, с запасным вариантом
        const previewPath = video.thumbnail_url ? 
            video.thumbnail_url : 
            `/static/placeholder.jpg`;
            
        const resultItem = document.createElement('div');
        resultItem.className = 'search-result';
        resultItem.innerHTML = `
            <div class="search-thumbnail">
                <img src="${previewPath}" onerror="this.src='/static/placeholder.jpg'" alt="${video.title}">
            </div>
            <div class="search-info">
                <div class="search-title">${video.title}</div>
                <div class="search-channel">${video.user_id || ''}</div>
            </div>
        `;
        
        resultItem.addEventListener('click', function() {
            window.location.href = `/video/${video.video_id}/`;
        });
        
        searchDropdown.appendChild(resultItem);
    });
    
    // Если есть больше результатов, добавляем ссылку "Показать все результаты"
    if (results.length > 5) {
        const showMore = document.createElement('div');
        showMore.className = 'search-more';
        showMore.textContent = 'Показать все результаты';
        
        showMore.addEventListener('click', function() {
            const searchInput = document.getElementById('search-input');
            if (searchInput) {
                // Перенаправление на страницу результатов поиска
                window.location.href = `/search?query=${encodeURIComponent(searchInput.value)}`;
            }
        });
        
        searchDropdown.appendChild(showMore);
    }
    
    searchDropdown.classList.add('show');
}

// Функция для настройки поиска
function setupSearch() {
    const searchInput = document.getElementById('search-input');
    const searchDropdown = document.getElementById('search-dropdown');
    const searchButton = document.querySelector('.search-button');
    
    if (!searchInput || !searchDropdown) return;
    
    // Обработчики событий для поиска
    searchInput.addEventListener('input', function() {
        const query = this.value;
        const results = searchVideos(query);
        showSearchResults(results, searchDropdown);
    });
    
    searchInput.addEventListener('focus', function() {
        if (this.value.trim()) {
            const results = searchVideos(this.value);
            showSearchResults(results, searchDropdown);
        }
    });
    
    document.addEventListener('click', function(e) {
        if (searchInput && searchDropdown && 
            !searchInput.contains(e.target) && 
            !searchDropdown.contains(e.target)) {
            searchDropdown.classList.remove('show');
        }
    });
    
    if (searchButton) {
        searchButton.addEventListener('click', function() {
            if (searchInput.value.trim()) {
                window.location.href = `/search?query=${encodeURIComponent(searchInput.value)}`;
            }
        });
    }
    
    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && this.value.trim()) {
            window.location.href = `/search?query=${encodeURIComponent(this.value)}`;
        }
    });
}

// Функция для настройки сворачивания/разворачивания боковой панели
function setupSidebar() {
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    const mainContainer = document.querySelector('.main-container');
    
    if (!sidebarToggle || !sidebar || !mainContainer) return;
    
    sidebarToggle.addEventListener('click', function() {
        sidebar.classList.toggle('collapsed');
        mainContainer.classList.toggle('expanded');
    });
}

// Function to make sidebar menu items active when clicked
function setupSidebarMenuItems() {
    const menuItems = document.querySelectorAll('.sidebar .menu-item');
    
    if (!menuItems.length) return;
    
    menuItems.forEach(item => {
        // Skip items that already have onclick handlers (like Studio and Home)
        if (item.getAttribute('onclick')) return;
        
        item.addEventListener('click', function() {
            // Remove active class from all items
            menuItems.forEach(i => i.classList.remove('active'));
            // Add active class to clicked item
            this.classList.add('active');
        });
    });
}

// Функция для настройки переключения темы
function setupThemeToggle() {
    const themeToggle = document.querySelector('.theme-toggle');
    const body = document.body;
    const themeTransition = document.querySelector('.theme-transition');
    const toggleText = document.querySelector('.toggle-text');
    
    if (!themeToggle || !themeTransition || !toggleText) return;
    
    // Загружаем сохраненную тему при загрузке страницы
    const savedTheme = localStorage.getItem('kronik-theme');
    if (savedTheme) {
        if (savedTheme === 'light') {
            body.classList.remove('dark-theme');
            body.classList.add('light-theme');
        } else {
            body.classList.remove('light-theme');
            body.classList.add('dark-theme');
        }
    }
    
    themeToggle.addEventListener('click', function() {
        const isDark = body.classList.contains('dark-theme');
        themeTransition.className = `theme-transition ${isDark ? 'light' : 'dark'} animating`;
        
        setTimeout(() => {
            body.classList.toggle('dark-theme');
            body.classList.toggle('light-theme');
            
            // Обновляем текст кнопки
            const newTheme = body.classList.contains('light-theme') ? 'light' : 'dark';
            
            // Сохраняем выбранную тему в localStorage
            localStorage.setItem('kronik-theme', newTheme);
        }, 500);
        
        setTimeout(() => {
            themeTransition.classList.remove('animating');
        }, 1500);
    });
}

// Функция для настройки пользовательского меню
function setupUserMenu() {
    const userMenu = document.querySelector('.user-menu');
    const userDropdown = document.querySelector('.user-dropdown');
    
    if (!userMenu || !userDropdown) return;
    
    userMenu.addEventListener('click', function(e) {
        e.stopPropagation();
        userDropdown.classList.toggle('show');
    });
    
    // Закрытие выпадающего меню по клику вне него
    document.addEventListener('click', function(e) {
        if (userMenu && userDropdown && 
            !userMenu.contains(e.target)) {
            userDropdown.classList.remove('show');
        }
    });
}

// Функция для настройки мобильного меню
function setupMobileMenu() {
    const mobileMenuButton = document.querySelector('.mobile-menu-button');
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.overlay');
    
    if (!sidebar || !overlay) return;
    
    if (mobileMenuButton) {
        mobileMenuButton.addEventListener('click', function() {
            sidebar.classList.toggle('show');
            overlay.classList.toggle('show');
        });
    }
    
    overlay.addEventListener('click', function() {
        sidebar.classList.remove('show');
        overlay.classList.remove('show');
    });
}

// Функция для настройки категорий
function setupCategories() {
    const categoryChips = document.querySelectorAll('.category-chip');
    
    if (!categoryChips.length || !videosContainer) return;
    
    categoryChips.forEach(chip => {
        chip.addEventListener('click', function() {
            // Убираем активный класс у всех элементов
            categoryChips.forEach(c => c.classList.remove('active'));
            // Добавляем активный класс к выбранному элементу
            this.classList.add('active');
            
            // Сбрасываем индекс для правильной загрузки
            currentIndex = 0;
            
            // Очищаем контейнер
            videosContainer.innerHTML = '';
            
            // Получаем выбранную категорию
            const category = this.textContent.toLowerCase();
            
            // Если выбрана категория "Все", загружаем все видео
            if (category === 'все') {
                // Загружаем первую партию видео
                for (let i = 0; i < Math.min(videosPerPage, videoData.length); i++) {
                    const card = createVideoCard(videoData[i], i * 100);
                    videosContainer.appendChild(card);
                    currentIndex++;
                }
            } else {
                // Фильтруем видео по категории
                const filteredVideos = videoData.filter(video => {
                    // Проверяем категорию видео (если она есть)
                    if (video.category) {
                        return video.category.toLowerCase().includes(category);
                    }
                    return false;
                });
                
                // Если нет видео в этой категории
                if (filteredVideos.length === 0) {
                    const emptyState = document.createElement('div');
                    emptyState.className = 'empty-state';
                    emptyState.innerHTML = `
                        <div style="text-align: center; padding: 40px 20px;">
                            <div style="font-size: 48px; margin-bottom: 20px;">🐰</div>
                            <h3>Нет видео в категории "${this.textContent}"</h3>
                            <p>Попробуйте выбрать другую категорию или загляните позже</p>
                        </div>
                    `;
                    videosContainer.appendChild(emptyState);
                } else {
                    // Добавляем отфильтрованные видео
                    for (let i = 0; i < Math.min(videosPerPage, filteredVideos.length); i++) {
                        const card = createVideoCard(filteredVideos[i], i * 100);
                        videosContainer.appendChild(card);
                    }
                }
            }
        });
    });
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Инициализация DOM-элементов
    loadingSpinner = document.getElementById('loading-spinner');
    videosContainer = document.getElementById('videos-container');
    
    // Загружаем реальные видео из GCS
    if (videosContainer && videosContainer.children.length === 0) {
        loadVideosFromGCS();
    }
    
    // Подписка на прокрутку для бесконечной загрузки
    window.addEventListener('scroll', handleScroll);
    
    // Настройка всех интерактивных элементов
    setupSearch();
    setupSidebar();
    setupThemeToggle();
    setupUserMenu();
    setupMobileMenu();
    setupCategories();
    setupSidebarMenuItems();
});