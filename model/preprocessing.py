import cv2
import numpy as np
import math
from skimage.filters import threshold_sauvola
from skimage.morphology import skeletonize

IMG_SIZE = 155

class SignaturePreprocessor:
    def __init__(self, out_size=IMG_SIZE):
        self.out_size = out_size
        self.clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))

    def _early_downsample(self, img, max_dim=350):
        h, w = img.shape[:2]
        if max(h, w) <= max_dim:
            return img
        scale = max_dim / max(h, w)
        return cv2.resize(img, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)

    def _order_points(self, pts):
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1); rect[0] = pts[np.argmin(s)]; rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1); rect[1] = pts[np.argmin(diff)]; rect[3] = pts[np.argmax(diff)]
        return rect

    def _four_point_transform(self, img, pts):
        rect = self._order_points(pts)
        (tl, tr, br, bl) = rect
        maxW = int(max(np.linalg.norm(br-bl), np.linalg.norm(tr-tl)))
        maxH = int(max(np.linalg.norm(tr-br), np.linalg.norm(tl-bl)))
        dst = np.array([[0,0],[maxW-1,0],[maxW-1,maxH-1],[0,maxH-1]], dtype=np.float32)
        M = cv2.getPerspectiveTransform(rect, dst)
        return cv2.warpPerspective(img, M, (maxW, maxH))

    def _localize_document(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.dilate(cv2.Canny(blur, 50, 150), np.ones((3,3), np.uint8), iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
        img_area = img.shape[0]*img.shape[1]
        for c in contours:
            approx = cv2.approxPolyDP(c, 0.02*cv2.arcLength(c, True), True)
            if len(approx) == 4 and cv2.contourArea(approx) > 0.3*img_area:
                return self._four_point_transform(img, approx.reshape(4,2).astype(np.float32))
        return img

    def _localize_signature_region(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        _, coarse = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
        coarse = cv2.morphologyEx(coarse, cv2.MORPH_CLOSE, np.ones((25,25), np.uint8))
        contours, _ = cv2.findContours(coarse, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours: return img
        c = max(contours, key=cv2.contourArea)
        x,y,w,h = cv2.boundingRect(c); pad = int(0.1*max(w,h))
        x0,y0 = max(0,x-pad), max(0,y-pad)
        x1,y1 = min(img.shape[1],x+w+pad), min(img.shape[0],y+h+pad)
        return img[y0:y1, x0:x1]

    def _clahe_normalize(self, gray): return self.clahe.apply(gray)

    def _sauvola_binarize(self, gray, window_size=25, k=0.2):
        thresh = threshold_sauvola(gray, window_size=window_size, k=k)
        return (gray < thresh).astype(np.uint8)*255

    def _filter_blobs_by_size(self, bin_img, min_area_frac=0.00005, max_area_frac=0.35):
        n, labels, stats, _ = cv2.connectedComponentsWithStats(bin_img, connectivity=8)
        if n <= 1: return bin_img
        h, w = bin_img.shape; img_area = h*w
        min_area, max_area = min_area_frac*img_area, max_area_frac*img_area
        clean = np.zeros_like(bin_img)
        for i in range(1, n):
            area = stats[i, cv2.CC_STAT_AREA]
            if min_area <= area <= max_area:
                clean[labels == i] = 255
        return clean

    def _hough_deskew_angle(self, bin_img):
        edges = cv2.Canny(bin_img, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=40,
                                 minLineLength=bin_img.shape[1]*0.15, maxLineGap=10)
        if lines is None or len(lines) == 0: return None
        angles = []
        for line in lines:
            x1,y1,x2,y2 = line[0]
            a = math.degrees(math.atan2(y2-y1, x2-x1))
            if -45 < a < 45: angles.append(a)
        return float(np.median(angles)) if angles else None

    def _minarea_deskew_angle(self, bin_img):
        ys, xs = np.where(bin_img > 0)
        if len(xs) < 20: return 0.0
        pts = np.column_stack([xs, ys]).astype(np.float32)
        angle = cv2.minAreaRect(pts)[-1]
        if angle < -45: angle = 90+angle
        if abs(angle) > 45: angle = angle-90 if angle > 0 else angle+90
        return angle

    def _deskew(self, bin_img):
        angle = self._hough_deskew_angle(bin_img)
        if angle is None: angle = self._minarea_deskew_angle(bin_img)
        h, w = bin_img.shape
        M = cv2.getRotationMatrix2D((w//2, h//2), angle, 1.0)
        return cv2.warpAffine(bin_img, M, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)

    def _crop_and_pad(self, bin_img):
        ys, xs = np.where(bin_img > 0)
        if len(xs) == 0:
            crop = bin_img
        else:
            pad = 10
            y0,y1 = max(0,ys.min()-pad), min(bin_img.shape[0],ys.max()+pad)
            x0,x1 = max(0,xs.min()-pad), min(bin_img.shape[1],xs.max()+pad)
            crop = bin_img[y0:y1, x0:x1]
        h, w = crop.shape
        scale = self.out_size / max(h, w)
        nh, nw = max(1,int(h*scale)), max(1,int(w*scale))
        resized = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA)
        canvas = np.zeros((self.out_size, self.out_size), dtype=np.uint8)
        oy, ox = (self.out_size-nh)//2, (self.out_size-nw)//2
        canvas[oy:oy+nh, ox:ox+nw] = resized
        return canvas

    def _normalize_stroke_width(self, bin_img, target_width=2):
        if bin_img.max() == 0: return bin_img
        skel = (skeletonize(bin_img > 0).astype(np.uint8))*255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (target_width, target_width))
        return cv2.dilate(skel, kernel, iterations=1)

    def process(self, img, already_cropped=True):
        img = self._early_downsample(img, max_dim=350)
        if img.ndim == 3:
            if not already_cropped:
                img = self._localize_document(img)
                img = self._localize_signature_region(img)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        gray = self._clahe_normalize(gray)
        bin_img = self._sauvola_binarize(gray)
        bin_img = self._filter_blobs_by_size(bin_img)
        bin_img = self._deskew(bin_img)
        bin_img = self._filter_blobs_by_size(bin_img)
        bin_img = self._normalize_stroke_width(bin_img)
        canvas = self._crop_and_pad(bin_img)
        return (canvas.astype(np.float32)/255.0)
