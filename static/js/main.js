function createVideoCard(videoData, delay = 0) {
    const card = document.createElement('div');
    card.className = 'video-card';
    card.style.animationDelay = `${delay}ms`;
    
    // Добавляем обработчик клика, который перенаправляет на страницу видео
    card.onclick = function() {
        // Используем составной ID: user_id + video_id
        const videoUrl = `/video/${videoData.user_id}__${videoData.video_id}/`;
        window.location.href = videoUrl;
    };

    // Определяем путь к превью, с запасным вариантом
    const previewPath = videoData.thumbnail_url ? 
        videoData.thumbnail_url : 
        `/static/placeholder.jpg`;

    // Определяем имя канала: предпочитаем display_name, затем channel, затем user_id
    const channelName = videoData.display_name || videoData.channel || videoData.user_id || "";
    
    // Используем только изображение превью вместо видео
    card.innerHTML = `
        <div class="thumbnail">
            <img src="${previewPath}" alt="${videoData.title}" loading="lazy" onerror="this.src='/static/placeholder.jpg'">
            <div class="duration">${videoData.duration || "00:00"}</div>
        </div>
        <div class="video-info">
            <div class="video-title">${videoData.title}</div>
            <div class="channel-name">${channelName}</div>
            <div class="video-stats">
                <span>${videoData.views_formatted || videoData.views || "0 просмотров"}</span>
                <span>• ${videoData.upload_date_formatted || (videoData.upload_date ? videoData.upload_date.slice(0, 10) : "Недавно")}</span>
            </div>
        </div>
    `;

    return card;
}

// Переменные для хранения реальных данных видео из GCS
let videoData = [];

// Переменные для управления загрузкой
let currentIndex = 0;
const videosPerPage = 15; // Показываем только 15 видео за раз для быстрой загрузки
let loadingSpinner, videosContainer;
let isLoading = false;

// Загрузка видео из GCS с оптимизацией
function loadVideosFromGCS() {
    if (isLoading) return;
    
    isLoading = true;
    if (loadingSpinner) loadingSpinner.style.display = 'flex';
    
    console.log("Loading videos from all users...");
    
    // Для отладки: проверим, что переменные определены
    if (!videosContainer) {
        console.error("videosContainer is not defined");
        return;
    }
    
    // Получаем API URL для списка видео
    fetch('/api/list-all-videos/')
        .then(response => {
            if (!response.ok) {
                throw new Error(`Server responded with status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            isLoading = false;
            if (loadingSpinner) loadingSpinner.style.display = 'none';
            
            console.log("API response:", data);
            
            if (data.success && data.videos && data.videos.length > 0) {
                // Сохраняем полученные видео
                videoData = data.videos;
                console.log(`Received ${videoData.length} videos`);
                
                // Перемешиваем видео для случайного порядка
                shuffleArray(videoData);
                
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
                }
            } else {
                console.log("No videos found or invalid data structure");
                
                // Показываем сообщение, если нет видео
                if (videosContainer) {
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
        })
        .catch(error => {
            isLoading = false;
            if (loadingSpinner) loadingSpinner.style.display = 'none';
            console.error('Ошибка при получении видео из GCS:', error);
            
            // Показываем сообщение об ошибке
            if (videosContainer) {
                videosContainer.innerHTML = `
                    <div style="text-align: center; padding: 40px 20px;">
                        <div style="font-size: 48px; margin-bottom: 20px;">⚠️</div>
                        <h3>Произошла ошибка при загрузке видео</h3>
                        <p>Пожалуйста, обновите страницу или попробуйте позже</p>
                        <p style="color: #999; font-size: 0.8rem;">Ошибка: ${error.message}</p>
                    </div>
                `;
            }
        });
}

// Функция для перемешивания массива (алгоритм Фишера-Йейтса)
function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
}

// Загрузка дополнительных видео с отложенной загрузкой изображений
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

// Оптимизированный обработчик прокрутки с дебаунсингом
let scrollTimeout;
function handleScroll() {
    if (scrollTimeout) clearTimeout(scrollTimeout);
    
    scrollTimeout = setTimeout(() => {
        if (!videosContainer) return;
        
        // Проверяем, достиг ли пользователь конца текущих видео
        const lastVideoCard = videosContainer.querySelector('.video-card:last-child');
        
        if (lastVideoCard) {
            const lastVideoRect = lastVideoCard.getBoundingClientRect();
            const offset = 200; // Загружаем немного раньше, чем пользователь достигнет конца
            
            // Загружаем новые видео когда последняя карточка приближается к области просмотра
            if (lastVideoRect.bottom <= window.innerHeight + offset && !isLoading) {
                loadMoreVideos();
            }
        }
    }, 100); // Дебаунсинг в 100мс для предотвращения слишком частых вызовов
}

// Функция для поиска видео
function searchVideos(query) {
    if (!query.trim() || !videoData.length) return [];
    
    query = query.toLowerCase();
    return videoData.filter(video => 
        (video.title && video.title.toLowerCase().includes(query)) || 
        (video.display_name && video.display_name.toLowerCase().includes(query)) ||
        (video.channel && video.channel.toLowerCase().includes(query)) ||
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
        
        // Определяем имя канала для отображения
        const channelName = video.display_name || video.channel || video.user_id || '';
            
        const resultItem = document.createElement('div');
        resultItem.className = 'search-result';
        resultItem.innerHTML = `
            <div class="search-thumbnail">
                <img src="${previewPath}" loading="lazy" onerror="this.src='/static/placeholder.jpg'" alt="${video.title}">
            </div>
            <div class="search-info">
                <div class="search-title">${video.title}</div>
                <div class="search-channel">${channelName}</div>
            </div>
        `;
        
        resultItem.addEventListener('click', function() {
            window.location.href = `/video/${video.user_id}__${video.video_id}/`;
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
    
    // Дебаунсинг для поиска при вводе
    let searchTimeout;
    searchInput.addEventListener('input', function() {
        if (searchTimeout) clearTimeout(searchTimeout);
        
        const query = this.value;
        
        // Если запрос пустой, скрываем результаты
        if (!query.trim()) {
            searchDropdown.classList.remove('show');
            return;
        }
        
        // Задержка перед поиском, чтобы не перегружать систему
        searchTimeout = setTimeout(() => {
            const results = searchVideos(query);
            showSearchResults(results, searchDropdown);
        }, 300);
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
            
            // Показываем спиннер загрузки
            if (loadingSpinner) loadingSpinner.style.display = 'flex';
            
            // Добавляем небольшую задержку для отображения UX загрузки
            setTimeout(() => {
                // Если выбрана категория "Все", загружаем все видео
                if (category === 'все') {
                    // Перемешиваем видео заново для разнообразия
                    shuffleArray(videoData);
                    
                    // Загружаем первую партию видео
                    for (let i = 0; i < Math.min(videosPerPage, videoData.length); i++) {
                        const card = createVideoCard(videoData[i], i * 50); // Уменьшаем задержку для быстрой загрузки
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
                    
                    // Перемешиваем отфильтрованные видео
                    shuffleArray(filteredVideos);
                    
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
                            const card = createVideoCard(filteredVideos[i], i * 50);
                            videosContainer.appendChild(card);
                        }
                    }
                }
                
                // Скрываем спиннер загрузки
                if (loadingSpinner) loadingSpinner.style.display = 'none';
            }, 300);
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
    
    // Подписка на прокрутку для бесконечной загрузки с использованием
    // passive: true для увеличения производительности прокрутки
    window.addEventListener('scroll', handleScroll, { passive: true });
    
    // Настройка всех интерактивных элементов
    setupSearch();
    setupSidebar();
    setupThemeToggle();
    setupUserMenu();
    setupMobileMenu();
    setupCategories();
    setupSidebarMenuItems();
});